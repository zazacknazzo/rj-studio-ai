from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock

from rj_studio_ai.delivery import OutboundDeliveryExecutor
from rj_studio_ai.domain import InboundMessage, OutboundMessage
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import OutboundMessageSender, ProviderAcceptance

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _pending(store: SqliteConversationStore, suffix: str) -> int:
    claim = store.claim_generation(
        InboundMessage(
            provider="test-provider",
            provider_message_id=f"inbound-{suffix}",
            customer_address=f"customer-{suffix}",
            recipient_address="studio-channel",
            body="Mensagem sintética",
        ),
        now=NOW,
    )
    assert claim.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta sintética",
        delivery_state=DeliveryState.PENDING,
        now=NOW + timedelta(seconds=1),
    )
    return claim.inbound_message_id


class _SignallingSender(OutboundMessageSender):
    def __init__(self) -> None:
        self.called = Event()
        self.calls: list[OutboundMessage] = []

    def send(
        self,
        message: OutboundMessage,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        self.calls.append(message)
        self.called.set()
        return ProviderAcceptance(provider_message_id="PM-executor")


class _BoundedSender(OutboundMessageSender):
    def __init__(self, expected_concurrent: int) -> None:
        self._lock = Lock()
        self._release = Event()
        self.expected_concurrent = expected_concurrent
        self.ready = Event()
        self.active = 0
        self.maximum_active = 0
        self.total_calls = 0

    def send(
        self,
        message: OutboundMessage,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        with self._lock:
            self.active += 1
            self.total_calls += 1
            call_number = self.total_calls
            self.maximum_active = max(self.maximum_active, self.active)
            if self.active == self.expected_concurrent:
                self.ready.set()
        assert self._release.wait(timeout=2.0)
        with self._lock:
            self.active -= 1
        return ProviderAcceptance(provider_message_id=f"PM-executor-{call_number}")

    def release(self) -> None:
        self._release.set()


def test_executor_recovers_pending_work_after_restart_and_stops_gracefully(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "executor-restart.db"
    initial_store = SqliteConversationStore(database_path)
    initial_store.initialize()
    inbound_id = _pending(initial_store, "restart")
    sender = _SignallingSender()
    executor = OutboundDeliveryExecutor(
        store=SqliteConversationStore(database_path),
        sender=sender,
        request_timeout_seconds=1.0,
        poll_interval_seconds=0.05,
        concurrency=1,
    )

    executor.start()
    assert executor.is_alive()
    assert sender.called.wait(timeout=2.0)
    executor.stop()

    assert not executor.is_alive()
    delivery = SqliteConversationStore(database_path).get_delivery_for_inbound(inbound_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.ACCEPTED
    assert len(sender.calls) == 1


def test_executor_never_exceeds_configured_concurrency(tmp_path: Path) -> None:
    database_path = tmp_path / "executor-concurrency.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    for suffix in ("a", "b", "c"):
        _pending(store, suffix)
    sender = _BoundedSender(expected_concurrent=2)
    executor = OutboundDeliveryExecutor(
        store=store,
        sender=sender,
        request_timeout_seconds=1.0,
        poll_interval_seconds=0.05,
        concurrency=2,
    )

    executor.start()
    assert sender.ready.wait(timeout=2.0)
    assert sender.total_calls == 2
    assert sender.maximum_active == 2
    sender.release()
    executor.wake()

    deadline = Event()
    for _ in range(100):
        if sender.total_calls == 3:
            break
        deadline.wait(0.01)
    executor.stop()

    assert sender.total_calls == 3
    assert sender.maximum_active == 2
