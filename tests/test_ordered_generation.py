import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rj_studio_ai.application import MessageResponder, RetryableWebhookError
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import GeneratedReply, GenerationTimeout, TransientGenerationError
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationClaimResult,
    GenerationState,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


class ScriptedGenerator:
    def __init__(
        self,
        actions: list[str | Exception | Callable[[float], str]],
    ) -> None:
        self._actions = iter(actions)
        self.budgets: list[float] = []

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        self.budgets.append(remaining_budget)
        action = next(self._actions)
        if isinstance(action, Exception):
            raise action
        if callable(action):
            return GeneratedReply.from_reply_text(action(remaining_budget))
        return GeneratedReply.from_reply_text(action)

    def is_configured(self) -> bool:
        return True


class AdvancingStore(SqliteConversationStore):
    def __init__(self, database_path: Path, clock: FakeClock) -> None:
        super().__init__(database_path)
        self._clock = clock
        self.lock_timeouts: list[float | None] = []

    def admit_generation(
        self,
        message: InboundMessage,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> GenerationClaimResult:
        self.lock_timeouts.append(lock_timeout)
        self._clock.advance(1.5)
        return super().admit_generation(message, now=now, lock_timeout=lock_timeout)

    def claim_generation(
        self,
        message: InboundMessage,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> GenerationClaimResult:
        self.lock_timeouts.append(lock_timeout)
        self._clock.advance(1.0)
        return super().claim_generation(message, now=now, lock_timeout=lock_timeout)


class BudgetExhaustingClaimStore(SqliteConversationStore):
    def __init__(self, database_path: Path, clock: FakeClock) -> None:
        super().__init__(database_path)
        self._clock = clock
        self.claim_lock_timeout: float | None = None

    def claim_generation(
        self,
        message: InboundMessage,
        *,
        now: datetime | None = None,
        lock_timeout: float | None = None,
    ) -> GenerationClaimResult:
        self.claim_lock_timeout = lock_timeout
        self._clock.advance(8.95)
        return super().claim_generation(message, now=now, lock_timeout=lock_timeout)


def _message(message_id: str, body: str = "Mensagem") -> InboundMessage:
    return InboundMessage(
        provider="test-provider",
        provider_message_id=message_id,
        customer_address="customer-1",
        recipient_address="studio",
        body=body,
    )


def _store(database_path: Path) -> SqliteConversationStore:
    store = SqliteConversationStore(database_path)
    store.initialize()
    return store


def _responder(
    store: SqliteConversationStore,
    generator: ScriptedGenerator,
    clock: FakeClock,
    **overrides: float,
) -> MessageResponder:
    return MessageResponder(
        store=store,
        generator=generator,
        safe_failure_reply="Resposta segura",
        sleeper=clock.sleep,
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
        **overrides,
    )


def test_deadline_uses_one_monotonic_budget_and_reserves_finalization_time() -> None:
    clock = FakeClock()
    deadline = ExecutionDeadline.start(
        clock=clock,
        total_seconds=10.0,
        finalization_margin_seconds=1.0,
    )

    clock.advance(2.25)

    assert deadline.remaining_budget() == pytest.approx(7.75)
    assert deadline.work_budget() == pytest.approx(6.75)


def test_time_spent_before_generation_reduces_the_supplied_budget(tmp_path: Path) -> None:
    clock = FakeClock()
    generator = ScriptedGenerator(["Resposta gerada"])
    responder = _responder(_store(tmp_path / "budget.db"), generator, clock)
    deadline = ExecutionDeadline.start(clock=clock)
    clock.advance(2.0)

    reply = responder.handle(_message("message-1"), deadline=deadline)

    assert reply.body == "Resposta gerada"
    assert generator.budgets == [pytest.approx(7.0)]


def test_sqlite_waits_consume_the_deadline_and_receive_only_remaining_budget(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    store = AdvancingStore(tmp_path / "sqlite-budget.db", clock)
    store.initialize()
    generator = ScriptedGenerator(["Resposta gerada"])
    responder = _responder(store, generator, clock)

    reply = responder.handle(
        _message("message-1"),
        deadline=ExecutionDeadline.start(clock=clock),
    )

    assert reply.body == "Resposta gerada"
    assert store.lock_timeouts[:2] == [pytest.approx(9.0), pytest.approx(7.4)]
    assert generator.budgets == [pytest.approx(6.5)]


def test_claim_that_consumes_useful_budget_releases_owner_without_generation(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    store = BudgetExhaustingClaimStore(tmp_path / "claim-budget.db", clock)
    store.initialize()
    generator = ScriptedGenerator(["Resposta indevida"])
    responder = _responder(store, generator, clock)

    with pytest.raises(RetryableWebhookError):
        responder.handle(
            _message("message-1"),
            deadline=ExecutionDeadline.start(clock=clock),
        )

    assert store.claim_lock_timeout == pytest.approx(8.9)
    assert generator.budgets == []
    lifecycle = store.get_generation(
        provider="test-provider",
        provider_message_id="message-1",
    )
    assert lifecycle is not None
    assert lifecycle.state is GenerationState.RETRYABLE
    assert lifecycle.owner_token is None
    assert lifecycle.attempt_count == 1


def test_transient_retry_and_backoff_consume_the_same_deadline(tmp_path: Path) -> None:
    clock = FakeClock()

    def fail_after_two_seconds(_: float) -> str:
        clock.advance(2.0)
        raise TransientGenerationError("synthetic transient failure")

    generator = ScriptedGenerator([fail_after_two_seconds, "Resposta recuperada"])
    responder = _responder(
        _store(tmp_path / "retry.db"),
        generator,
        clock,
        retry_backoff_seconds=0.25,
    )

    reply = responder.handle(
        _message("message-1"),
        deadline=ExecutionDeadline.start(clock=clock),
    )

    assert reply.body == "Resposta recuperada"
    assert generator.budgets == [pytest.approx(9.0), pytest.approx(6.75)]
    assert clock.value == pytest.approx(2.25)


def test_generation_does_not_start_when_only_finalization_margin_remains(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    generator = ScriptedGenerator(["Resposta indevida"])
    store = _store(tmp_path / "margin.db")
    responder = _responder(store, generator, clock)
    deadline = ExecutionDeadline.start(clock=clock)
    clock.advance(8.95)

    with pytest.raises(RetryableWebhookError):
        responder.handle(_message("message-1"), deadline=deadline)

    assert generator.budgets == []
    lifecycle = store.get_generation(
        provider="test-provider",
        provider_message_id="message-1",
    )
    assert lifecycle is not None
    assert lifecycle.state is GenerationState.RETRYABLE
    assert lifecycle.attempt_count == 0


def test_later_message_waits_then_generates_after_predecessor_finishes(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    store = _store(tmp_path / "ordered.db")
    first = store.claim_generation(_message("message-1", "Primeira"))
    assert first.owner_token is not None
    generator = ScriptedGenerator(["Resposta da segunda"])
    completed_predecessor = False

    def finish_predecessor(seconds: float) -> None:
        nonlocal completed_predecessor
        clock.advance(seconds)
        if not completed_predecessor:
            completed_predecessor = store.complete_generation(
                inbound_message_id=first.inbound_message_id,
                owner_token=first.owner_token or "",
                reply_body="Resposta da primeira",
                delivery_state=DeliveryState.ACCEPTED_LEGACY,
            )

    responder = MessageResponder(
        store=store,
        generator=generator,
        safe_failure_reply="Resposta segura",
        sleeper=finish_predecessor,
        ordering_poll_seconds=0.1,
        maximum_ordering_wait_seconds=1.0,
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
    )

    reply = responder.handle(
        _message("message-2", "Segunda"),
        deadline=ExecutionDeadline.start(clock=clock),
    )

    assert completed_predecessor
    assert reply.body == "Resposta da segunda"
    assert generator.budgets == [pytest.approx(8.9)]
    history = store.get_history(provider="test-provider", customer_address="customer-1")
    assert [(item.direction, item.body) for item in history] == [
        ("inbound", "Primeira"),
        ("inbound", "Segunda"),
        ("outbound", "Resposta da primeira"),
        ("outbound", "Resposta da segunda"),
    ]


def test_blocked_message_is_persisted_and_a_later_webhook_retry_processes_it(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    store = _store(tmp_path / "blocked.db")
    first = store.claim_generation(_message("message-1", "Primeira"))
    assert first.owner_token is not None
    generator = ScriptedGenerator(["Resposta da segunda"])
    responder = _responder(
        store,
        generator,
        clock,
        ordering_poll_seconds=0.1,
        maximum_ordering_wait_seconds=0.3,
    )

    with pytest.raises(RetryableWebhookError):
        responder.handle(
            _message("message-2", "Segunda"),
            deadline=ExecutionDeadline.start(clock=clock),
        )

    blocked = store.get_generation(
        provider="test-provider",
        provider_message_id="message-2",
    )
    assert blocked is not None
    assert blocked.state is GenerationState.RETRYABLE
    assert blocked.attempt_count == 0
    assert generator.budgets == []
    assert clock.value == pytest.approx(0.3)

    assert store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta da primeira",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
    )
    retry_reply = responder.handle(
        _message("message-2", "Segunda alterada no retry"),
        deadline=ExecutionDeadline.start(clock=clock),
    )

    assert retry_reply.body == "Resposta da segunda"
    assert len(generator.budgets) == 1


def test_later_generation_waits_for_predecessor_provider_acceptance(tmp_path: Path) -> None:
    store = _store(tmp_path / "delivery-barrier.db")
    first = store.claim_generation(_message("message-1", "Primeira"), now=NOW)
    assert first.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta da primeira",
        delivery_state=DeliveryState.PENDING,
        now=NOW,
    )

    blocked = store.claim_generation(_message("message-2", "Segunda"), now=NOW)

    assert not blocked.acquired
    assert blocked.blocked_by_predecessor
    OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-first")]),
        timeout_seconds=1.0,
    ).run_once(now=NOW)

    acquired = store.claim_generation(_message("message-2", "Segunda"), now=NOW)
    assert acquired.acquired


def test_accepted_then_failed_delivery_blocks_future_generation(tmp_path: Path) -> None:
    database_path = tmp_path / "accepted-failed.db"
    store = _store(database_path)
    first = store.claim_generation(_message("message-1", "Primeira"), now=NOW)
    assert first.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta da primeira",
        delivery_state=DeliveryState.PENDING,
        now=NOW,
    )
    OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-first")]),
        timeout_seconds=1.0,
    ).run_once(now=NOW)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE outbound_deliveries
            SET state = 'failed', safe_error_code = 'provider_later_failed', updated_at = ?
            """,
            (NOW.isoformat(),),
        )

    later = store.claim_generation(_message("message-2", "Segunda"), now=NOW)

    assert not later.acquired
    assert later.blocked_by_predecessor


@pytest.mark.parametrize(
    "failure",
    [
        GenerationTimeout("synthetic timeout"),
    ],
)
def test_two_failed_attempts_persist_one_safe_terminal_reply(
    tmp_path: Path,
    failure: Exception | str,
) -> None:
    clock = FakeClock()
    store = _store(tmp_path / "safe-failure.db")
    generator = ScriptedGenerator([failure, failure])
    responder = _responder(store, generator, clock)

    reply = responder.handle(
        _message("message-1"),
        deadline=ExecutionDeadline.start(clock=clock),
    )

    assert reply.body == "Resposta segura"
    lifecycle = store.get_generation(
        provider="test-provider",
        provider_message_id="message-1",
    )
    assert lifecycle is not None
    assert lifecycle.state is GenerationState.COMPLETED
    assert lifecycle.attempt_count == 2
    assert lifecycle.reply_body == "Resposta segura"
    assert len(store.get_history(provider="test-provider", customer_address="customer-1")) == 2


def test_provider_retry_finalizes_exhausted_work_without_a_third_generation(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    store = _store(tmp_path / "exhausted-retry.db")
    message = _message("message-1")
    first = store.claim_generation(message)
    assert first.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
    )
    second = store.claim_generation(message)
    assert second.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=second.inbound_message_id,
        owner_token=second.owner_token,
    )
    generator = ScriptedGenerator([])
    responder = _responder(store, generator, clock)

    reply = responder.handle(message, deadline=ExecutionDeadline.start(clock=clock))

    assert reply.body == "Resposta segura"
    assert generator.budgets == []
    terminal = store.get_generation(
        provider="test-provider",
        provider_message_id="message-1",
    )
    assert terminal is not None
    assert terminal.state is GenerationState.COMPLETED
    assert terminal.attempt_count == 2


def test_webhook_deadline_remains_independent_from_generation_lease(tmp_path: Path) -> None:
    store = _store(tmp_path / "lease.db")
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

    claim = store.claim_generation(_message("message-1"), now=now)

    assert ExecutionDeadline.DEFAULT_TOTAL_SECONDS == 10.0
    assert claim.lease_expires_at is not None
    assert (claim.lease_expires_at - now).total_seconds() == 30.0
