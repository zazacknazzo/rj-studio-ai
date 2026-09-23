from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock

import pytest

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import DeliveryStatus, DeliveryStatusReceived, InboundMessage
from rj_studio_ai.generation import FixedReplyGenerator, GeneratedReply, TransientGenerationError
from rj_studio_ai.persistence import DeliveryState, GenerationState, SqliteConversationStore
from rj_studio_ai.processing import ProcessingExecutor, ProcessingRunner
from rj_studio_ai.providers.base import (
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender


def _message(identifier: str, customer: str = "customer-a") -> InboundMessage:
    return InboundMessage(
        provider="test-provider",
        provider_message_id=identifier,
        customer_address=customer,
        recipient_address="studio",
        body=f"Pergunta {identifier}",
    )


def _runner(store: SqliteConversationStore) -> ProcessingRunner:
    return ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=FixedReplyGenerator("Resposta sintética"),
            safe_failure_reply="Resposta segura",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    )


def test_persisted_inbound_is_processed_after_restart_without_provider_retry(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "async-restart.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    admitted = store.admit_generation(_message("first"))
    assert admitted.state is GenerationState.RETRYABLE
    assert admitted.reply_body is None

    restarted = SqliteConversationStore(database_path)
    result = _runner(restarted).run_once()

    assert result is not None
    assert result.inbound_message_id == admitted.inbound_message_id
    assert (
        restarted.get_generation(provider="test-provider", provider_message_id="first").state
        is GenerationState.COMPLETED
    )
    delivery = restarted.get_delivery_for_inbound(admitted.inbound_message_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.PENDING
    assert _runner(restarted).run_once() is None


def test_later_inbound_waits_for_provider_acceptance_while_other_conversation_runs(
    tmp_path: Path,
) -> None:
    store = SqliteConversationStore(tmp_path / "ordering.db")
    store.initialize()
    first = store.admit_generation(_message("first"))
    second = store.admit_generation(_message("second"))
    independent = store.admit_generation(_message("other", "customer-b"))
    runner = _runner(store)

    assert runner.run_once().inbound_message_id == first.inbound_message_id
    assert store.get_delivery_for_inbound(first.inbound_message_id).state is DeliveryState.PENDING
    assert runner.run_once().inbound_message_id == independent.inbound_message_id
    assert runner.run_once() is None
    assert (
        store.get_generation(provider="test-provider", provider_message_id="second").state
        is GenerationState.RETRYABLE
    )

    OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(
            outcomes=[ProviderAcceptance(provider_message_id="PM-first")]
        ),
        timeout_seconds=1.0,
    ).run_once()

    assert runner.run_once().inbound_message_id == second.inbound_message_id


def test_stale_generation_claim_is_recovered_by_polling(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "stale.db")
    store.initialize()
    old = datetime.now(UTC) - timedelta(minutes=1)
    stale = store.claim_generation(_message("stale"), now=old)
    assert stale.state is GenerationState.PROCESSING

    result = _runner(store).run_once()

    assert result is not None
    assert result.inbound_message_id == stale.inbound_message_id
    assert result.attempt_count == 2
    assert store.get_delivery_for_inbound(stale.inbound_message_id).state is DeliveryState.PENDING


class _ConcurrentGenerator:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self._lock = Lock()
        self.calls = 0

    def generate(
        self, message: InboundMessage, *, context: object, remaining_budget: float
    ) -> GeneratedReply:
        with self._lock:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=2.0)
        return GeneratedReply.from_reply_text("Resposta concorrente")

    def is_configured(self) -> bool:
        return True


def test_concurrent_processors_claim_one_inbound_once(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "concurrent.db")
    store.initialize()
    admitted = store.admit_generation(_message("same"))
    generator = _ConcurrentGenerator()
    runner = ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=generator,
            safe_failure_reply="Resposta segura",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runner.run_once)
        assert generator.entered.wait(timeout=2.0)
        second = pool.submit(runner.run_once)
        assert second.result(timeout=2.0) is None
        generator.release.set()
        assert first.result(timeout=2.0) is not None

    assert generator.calls == 1
    assert store.get_delivery_for_inbound(admitted.inbound_message_id) is not None
    assert len(store.get_history(provider="test-provider", customer_address="customer-a")) == 2


class _SelectiveBlockingGenerator:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def generate(
        self, message: InboundMessage, *, context: object, remaining_budget: float
    ) -> GeneratedReply:
        if message.customer_address == "customer-a":
            self.entered.set()
            assert self.release.wait(timeout=2.0)
        return GeneratedReply.from_reply_text(f"Resposta {message.customer_address}")

    def is_configured(self) -> bool:
        return True


def test_another_conversation_progresses_while_first_llm_is_active(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "independent.db")
    store.initialize()
    first = store.admit_generation(_message("first"))
    second = store.admit_generation(_message("second", "customer-b"))
    generator = _SelectiveBlockingGenerator()
    runner = ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=generator,
            safe_failure_reply="Resposta segura",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        blocked = pool.submit(runner.run_once)
        assert generator.entered.wait(timeout=2.0)
        independent = pool.submit(runner.run_once)
        assert independent.result(timeout=2.0).inbound_message_id == second.inbound_message_id
        generator.release.set()
        assert blocked.result(timeout=2.0).inbound_message_id == first.inbound_message_id


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _RetryingGenerator:
    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock
        self.budgets: list[float] = []

    def generate(
        self, message: InboundMessage, *, context: object, remaining_budget: float
    ) -> GeneratedReply:
        self.budgets.append(remaining_budget)
        self.clock.sleep(1.0)
        if len(self.budgets) == 1:
            raise TransientGenerationError("synthetic_retry")
        return GeneratedReply.from_reply_text("Resposta após retry")

    def is_configured(self) -> bool:
        return True


def test_processing_attempts_share_one_budget_after_claim(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "deadline.db")
    store.initialize()
    store.admit_generation(_message("deadline"))
    clock = _FakeClock()
    generator = _RetryingGenerator(clock)
    runner = ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=generator,
            safe_failure_reply="Resposta segura",
            completion_delivery_state=DeliveryState.PENDING,
            sleeper=clock.sleep,
        ),
        monotonic_clock=clock,
    )

    result = runner.run_once()

    assert result is not None
    assert result.state is GenerationState.COMPLETED
    assert generator.budgets[0] == 9.0
    assert generator.budgets[1] < generator.budgets[0]
    assert generator.budgets[1] > 0


@pytest.mark.parametrize(
    ("delivery_outcome", "can_advance"),
    [
        ("pending", False),
        ("sending", False),
        ("retryable", False),
        ("unknown", False),
        ("failed", False),
        ("accepted", True),
    ],
)
def test_processing_barrier_uses_delivery_acceptance(
    tmp_path: Path, delivery_outcome: str, can_advance: bool
) -> None:
    store = SqliteConversationStore(tmp_path / f"barrier-{delivery_outcome}.db")
    store.initialize()
    first = store.admit_generation(_message("first"))
    second = store.admit_generation(_message("second"))
    runner = _runner(store)
    assert runner.run_once().inbound_message_id == first.inbound_message_id

    if delivery_outcome == "sending":
        assert store.claim_next_delivery() is not None
    elif delivery_outcome != "pending":
        outcomes = {
            "retryable": OutboundRetryableError("proved not accepted"),
            "unknown": OutboundOutcomeUnknown("ambiguous"),
            "failed": OutboundPermanentError("rejected"),
            "accepted": ProviderAcceptance("PM-accepted"),
        }
        OutboundDeliveryRunner(
            store=store,
            sender=DeterministicFakeOutboundSender(outcomes=[outcomes[delivery_outcome]]),
            timeout_seconds=1.0,
        ).run_once()

    next_result = runner.run_once()
    assert (next_result is not None) is can_advance
    assert store.get_generation(provider="test-provider", provider_message_id="second").state is (
        GenerationState.COMPLETED if can_advance else GenerationState.RETRYABLE
    )
    if can_advance:
        assert next_result.inbound_message_id == second.inbound_message_id


def test_executor_polls_durable_work_after_restart_and_stops_new_claims(tmp_path: Path) -> None:
    database_path = tmp_path / "worker-restart.db"
    original = SqliteConversationStore(database_path)
    original.initialize()
    first = original.admit_generation(_message("first"))
    restarted = SqliteConversationStore(database_path)
    runner = _runner(restarted)
    executor = ProcessingExecutor(runner=runner, poll_interval_seconds=0.05, concurrency=1)

    executor.start()
    finished = Event()
    for _ in range(40):
        if restarted.get_delivery_for_inbound(first.inbound_message_id) is not None:
            finished.set()
            break
        finished.wait(0.05)
    assert finished.is_set()
    executor.stop()
    assert not executor.is_alive()

    later = restarted.admit_generation(_message("later", "customer-b"))
    assert restarted.get_delivery_for_inbound(later.inbound_message_id) is None
    assert (
        restarted.get_generation(provider="test-provider", provider_message_id="later").state
        is GenerationState.RETRYABLE
    )


class _BrokenRunner:
    def run_once(self) -> None:
        raise RuntimeError("synthetic failure without private data")


def test_unexpected_processing_loop_failure_makes_executor_unready() -> None:
    executor = ProcessingExecutor(runner=_BrokenRunner(), poll_interval_seconds=0.01, concurrency=1)

    executor.start()
    stopped = Event()
    for _ in range(40):
        if not executor.is_alive():
            stopped.set()
            break
        stopped.wait(0.01)
    executor.stop()

    assert stopped.is_set()


class _FailureBetweenClaimsStore(SqliteConversationStore):
    def claim_generation(self, message: InboundMessage, **kwargs: object):
        claim = super().claim_generation(message, **kwargs)
        if message.provider_message_id == "second" and claim.attempt_count == 2:
            self.record_delivery_status(
                DeliveryStatusReceived(
                    provider="test-provider",
                    provider_message_id="PM-first",
                    status=DeliveryStatus.FAILED,
                    safe_error_code="provider_failed",
                )
            )
        return claim


def test_exhausted_finalization_rechecks_predecessor_after_failure_race(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "exhausted-race.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    first = store.admit_generation(_message("first"))
    assert _runner(store).run_once() is not None
    OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-first")]),
        timeout_seconds=1.0,
    ).run_once()
    second_message = _message("second")
    second = store.claim_generation(second_message)
    assert second.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=second.inbound_message_id, owner_token=second.owner_token
    )
    second = store.claim_generation(second_message)
    assert second.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=second.inbound_message_id, owner_token=second.owner_token
    )
    racing_store = _FailureBetweenClaimsStore(database_path)
    responder = MessageResponder(
        store=racing_store,
        generator=FixedReplyGenerator("Nunca enviar"),
        safe_failure_reply="Resposta segura",
        completion_delivery_state=DeliveryState.PENDING,
    )

    reply = responder.process_persisted(second_message)

    assert reply is None
    assert racing_store.get_delivery_for_inbound(second.inbound_message_id) is None
    assert (
        racing_store.get_delivery_for_inbound(first.inbound_message_id).state
        is DeliveryState.FAILED
    )
