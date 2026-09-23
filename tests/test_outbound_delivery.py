import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import InboundMessage, OutboundMessage
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import (
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def _message(message_id: str = "SM-inbound", customer: str = "customer-1") -> InboundMessage:
    return InboundMessage(
        provider="test-provider",
        provider_message_id=message_id,
        customer_address=customer,
        recipient_address="studio-channel",
        body="Mensagem sintética",
    )


def _store(database_path: Path) -> SqliteConversationStore:
    store = SqliteConversationStore(database_path)
    store.initialize()
    return store


def _pending_completion(
    store: SqliteConversationStore,
    message: InboundMessage | None = None,
    *,
    now: datetime = NOW,
):
    claim = store.claim_generation(message or _message(), now=now)
    assert claim.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta persistida",
        delivery_state=DeliveryState.PENDING,
        now=now + timedelta(seconds=1),
    )
    delivery = store.get_delivery_for_inbound(claim.inbound_message_id)
    assert delivery is not None
    return claim, delivery


def test_generation_completion_atomically_creates_pending_delivery(tmp_path: Path) -> None:
    store = _store(tmp_path / "atomic.db")

    claim, delivery = _pending_completion(store)
    generation = store.get_generation(
        provider=_message().provider,
        provider_message_id=_message().provider_message_id,
    )

    assert generation is not None
    assert generation.state is GenerationState.COMPLETED
    assert generation.reply_body == "Resposta persistida"
    assert delivery.state is DeliveryState.PENDING
    assert delivery.provider == "test-provider"
    assert delivery.provider_channel_id == "studio-channel"
    assert delivery.recipient_address == "customer-1"
    assert delivery.attempt_count == 0
    assert delivery.owner_token is None
    assert delivery.next_attempt_at == NOW + timedelta(seconds=1)
    assert delivery.inbound_message_id == claim.inbound_message_id


def test_generation_completion_defaults_to_unverified_legacy_delivery(tmp_path: Path) -> None:
    store = _store(tmp_path / "legacy.db")
    claim = store.claim_generation(_message(), now=NOW)
    assert claim.owner_token is not None

    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta legada",
        now=NOW + timedelta(seconds=1),
    )

    delivery = store.get_delivery_for_inbound(claim.inbound_message_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.UNKNOWN
    assert delivery.safe_error_code == "legacy_unverified"
    assert delivery.accepted_at is None


def test_legacy_compatibility_reply_does_not_assume_render_evidence(tmp_path: Path) -> None:
    store = _store(tmp_path / "legacy-compatibility.db")

    assert store.get_or_create_reply(_message(), "Resposta legada") == "Resposta legada"

    generation = store.get_generation(
        provider=_message().provider,
        provider_message_id=_message().provider_message_id,
    )
    assert generation is not None
    delivery = store.get_delivery_for_inbound(generation.inbound_message_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.UNKNOWN
    assert delivery.safe_error_code == "legacy_unverified"


@pytest.mark.parametrize(
    ("trigger_sql", "trigger_name"),
    [
        (
            """
            CREATE TRIGGER fail_after_ai_reply
            BEFORE INSERT ON outbound_deliveries
            BEGIN
                SELECT RAISE(ABORT, 'synthetic delivery insert failure');
            END
            """,
            "fail_after_ai_reply",
        ),
        (
            """
            CREATE TRIGGER fail_after_delivery
            BEFORE UPDATE OF state ON message_processing
            WHEN NEW.state = 'completed'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic processing completion failure');
            END
            """,
            "fail_after_delivery",
        ),
    ],
)
def test_atomic_completion_rolls_back_every_partial_boundary(
    tmp_path: Path,
    trigger_sql: str,
    trigger_name: str,
) -> None:
    database_path = tmp_path / f"{trigger_name}.db"
    store = _store(database_path)
    claim = store.claim_generation(_message(), now=NOW)
    assert claim.owner_token is not None
    with sqlite3.connect(database_path) as connection:
        connection.execute(trigger_sql)

    with pytest.raises(PersistenceUnavailable):
        store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Resposta parcial",
            delivery_state=DeliveryState.PENDING,
            now=NOW + timedelta(seconds=1),
        )

    generation = store.get_generation(
        provider=_message().provider,
        provider_message_id=_message().provider_message_id,
    )
    assert generation is not None
    assert generation.state is GenerationState.PROCESSING
    assert generation.reply_body is None
    assert store.get_delivery_for_inbound(claim.inbound_message_id) is None
    assert [
        (item.direction, item.body)
        for item in store.get_history(
            provider=_message().provider,
            customer_address=_message().customer_address,
        )
    ] == [("inbound", "Mensagem sintética")]


def test_replay_does_not_create_a_second_logical_delivery(tmp_path: Path) -> None:
    database_path = tmp_path / "replay.db"
    store = _store(database_path)
    claim, first_delivery = _pending_completion(store)

    replay = SqliteConversationStore(database_path).claim_generation(
        _message(),
        now=NOW + timedelta(days=1),
    )
    replayed_delivery = SqliteConversationStore(database_path).get_delivery_for_inbound(
        claim.inbound_message_id
    )

    assert replay.state is GenerationState.COMPLETED
    assert replayed_delivery == first_delivery
    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM outbound_deliveries").fetchone()[0]
    assert count == 1


def test_database_rejects_second_delivery_for_one_ai_reply(tmp_path: Path) -> None:
    database_path = tmp_path / "unique-delivery.db"
    store = _store(database_path)
    _, delivery = _pending_completion(store)

    with sqlite3.connect(database_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO outbound_deliveries (
                outbound_message_id, provider, provider_channel_id, recipient_address,
                state, attempt_count, next_attempt_at, created_at, updated_at
            )
            SELECT outbound_message_id, provider, provider_channel_id, recipient_address,
                   'pending', 0, ?, ?, ?
            FROM outbound_deliveries WHERE id = ?
            """,
            (NOW.isoformat(), NOW.isoformat(), NOW.isoformat(), delivery.delivery_id),
        )


def test_database_rejects_delivery_without_valid_ai_reply(tmp_path: Path) -> None:
    database_path = tmp_path / "orphan-delivery.db"
    _store(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO conversations (
                provider, customer_address, created_at, updated_at
            ) VALUES ('test-provider', 'customer-1', ?, ?)
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        outbound_message_id = connection.execute(
            """
            INSERT INTO messages (
                conversation_id, provider, direction, body, created_at
            ) VALUES (1, 'test-provider', 'outbound', 'orphan', ?)
            RETURNING id
            """,
            (NOW.isoformat(),),
        ).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="valid AI Reply"):
            connection.execute(
                """
                INSERT INTO outbound_deliveries (
                    outbound_message_id, provider, provider_channel_id,
                    recipient_address, state, attempt_count, next_attempt_at,
                    created_at, updated_at
                ) VALUES (?, 'test-provider', 'studio', 'customer-1', 'pending', 0, ?, ?, ?)
                """,
                (
                    outbound_message_id,
                    NOW.isoformat(),
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )


def test_database_rejects_ai_reply_linked_across_conversations(tmp_path: Path) -> None:
    database_path = tmp_path / "cross-conversation-delivery.db"
    _store(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (?, 'test-provider', ?, ?, ?)
            """,
            [
                (1, "customer-a", NOW.isoformat(), NOW.isoformat()),
                (2, "customer-b", NOW.isoformat(), NOW.isoformat()),
            ],
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                recipient_address, direction, body, created_at
            ) VALUES (
                1, 1, 'test-provider', 'SM-cross', 'studio',
                'inbound', 'inbound', ?
            )
            """,
            (NOW.isoformat(),),
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, direction, body, created_at,
                in_reply_to_message_id
            ) VALUES (2, 2, 'test-provider', 'outbound', 'reply', ?, 1)
            """,
            (NOW.isoformat(),),
        )
        with pytest.raises(sqlite3.IntegrityError, match="valid AI Reply"):
            connection.execute(
                """
                INSERT INTO outbound_deliveries (
                    outbound_message_id, provider, provider_channel_id,
                    recipient_address, state, attempt_count, next_attempt_at,
                    created_at, updated_at
                ) VALUES (
                    2, 'test-provider', 'studio', 'customer-b',
                    'pending', 0, ?, ?, ?
                )
                """,
                (NOW.isoformat(), NOW.isoformat(), NOW.isoformat()),
            )


def test_database_protects_delivery_linked_message_identity(tmp_path: Path) -> None:
    database_path = tmp_path / "delivery-message-identity.db"
    store = _store(database_path)
    claim, delivery = _pending_completion(store)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (99, 'test-provider', 'other-customer', ?, ?)
            """,
            (NOW.isoformat(), NOW.isoformat()),
        )
        with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
            connection.execute(
                "UPDATE messages SET conversation_id = 99 WHERE id = ?",
                (delivery.outbound_message_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
            connection.execute(
                "UPDATE messages SET conversation_id = 99 WHERE id = ?",
                (claim.inbound_message_id,),
            )


def test_database_rejects_malformed_delivery_attempt_outcome(tmp_path: Path) -> None:
    database_path = tmp_path / "attempt-evidence.db"
    store = _store(database_path)
    _, delivery = _pending_completion(store)
    claim = store.claim_next_delivery(now=NOW + timedelta(seconds=1))
    assert claim is not None

    with sqlite3.connect(database_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE delivery_attempts
            SET outcome = 'accepted', completed_at = ?
            WHERE outbound_delivery_id = ? AND attempt_number = 1
            """,
            ((NOW + timedelta(seconds=2)).isoformat(), delivery.delivery_id),
        )

    with sqlite3.connect(database_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE delivery_attempts
            SET owner_token = 'replacement-owner'
            WHERE outbound_delivery_id = ? AND attempt_number = 1
            """,
            (delivery.delivery_id,),
        )

    with sqlite3.connect(database_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE delivery_attempts
            SET outcome = 'accepted',
                provider_message_id = 'PM-after-lease',
                completed_at = ?
            WHERE outbound_delivery_id = ? AND attempt_number = 1
            """,
            ((NOW + timedelta(seconds=32)).isoformat(), delivery.delivery_id),
        )


def test_pending_delivery_survives_logical_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "restart.db"
    _, delivery = _pending_completion(_store(database_path))

    after_restart = SqliteConversationStore(database_path).get_delivery(delivery.delivery_id)

    assert after_restart == delivery


def test_accepted_delivery_survives_restart_and_is_not_reprocessed(tmp_path: Path) -> None:
    database_path = tmp_path / "accepted-restart.db"
    store = _store(database_path)
    _pending_completion(store)
    sender = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-restart")])
    accepted = OutboundDeliveryRunner(
        store=store,
        sender=sender,
        timeout_seconds=1.0,
    ).run_once(now=NOW + timedelta(seconds=2))
    assert accepted is not None

    restarted = SqliteConversationStore(database_path)
    assert restarted.get_delivery(accepted.delivery_id).state is DeliveryState.ACCEPTED  # type: ignore[union-attr]
    assert restarted.claim_next_delivery(now=NOW + timedelta(days=1)) is None


def test_terminal_delivery_state_cannot_regress_to_pending(tmp_path: Path) -> None:
    database_path = tmp_path / "terminal-state.db"
    store = _store(database_path)
    _pending_completion(store)
    accepted = OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-terminal-state")]),
        timeout_seconds=1.0,
    ).run_once(now=NOW + timedelta(seconds=2))
    assert accepted is not None

    with sqlite3.connect(database_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            UPDATE outbound_deliveries
            SET state = 'pending',
                next_attempt_at = ?,
                provider_message_id = NULL,
                accepted_at = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (
                (NOW + timedelta(days=1)).isoformat(),
                (NOW + timedelta(days=1)).isoformat(),
                accepted.delivery_id,
            ),
        )


def test_concurrent_delivery_claim_has_exactly_one_owner(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent-claim.db"
    _, delivery = _pending_completion(_store(database_path))
    barrier = Barrier(2)

    def claim(_: int):
        barrier.wait()
        return SqliteConversationStore(database_path).claim_next_delivery(
            now=NOW + timedelta(seconds=2)
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, range(2)))

    acquired = [claim for claim in claims if claim is not None]
    assert len(acquired) == 1
    assert acquired[0].delivery_id == delivery.delivery_id
    assert acquired[0].state is DeliveryState.SENDING
    assert acquired[0].owner_token is not None
    assert acquired[0].attempt_count == 1


def test_wrong_and_stale_delivery_owner_cannot_finalize(tmp_path: Path) -> None:
    store = _store(tmp_path / "stale-owner.db")
    _, delivery = _pending_completion(store)
    claim = store.claim_next_delivery(now=NOW + timedelta(seconds=2))
    assert claim is not None
    assert claim.owner_token is not None

    assert not store.finalize_delivery(
        delivery_id=delivery.delivery_id,
        owner_token="wrong-owner",
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="PM-wrong",
        now=NOW + timedelta(seconds=3),
    )
    assert not store.finalize_delivery(
        delivery_id=delivery.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="PM-stale",
        now=NOW + timedelta(seconds=32),
    )
    assert store.get_delivery(delivery.delivery_id).state is DeliveryState.SENDING  # type: ignore[union-attr]


def test_expired_sending_becomes_unknown_and_is_not_reclaimed(tmp_path: Path) -> None:
    database_path = tmp_path / "expired-sending.db"
    store = _store(database_path)
    _, delivery = _pending_completion(store)
    claim = store.claim_next_delivery(now=NOW + timedelta(seconds=2))
    assert claim is not None

    after_restart = SqliteConversationStore(database_path)
    assert after_restart.claim_next_delivery(now=NOW + timedelta(seconds=33)) is None
    expired = after_restart.get_delivery(delivery.delivery_id)
    attempts = after_restart.get_delivery_attempts(delivery.delivery_id)

    assert expired is not None
    assert expired.state is DeliveryState.UNKNOWN
    assert expired.owner_token is None
    assert expired.safe_error_code == "sending_lease_expired"
    assert [attempt.outcome for attempt in attempts] == ["unknown"]
    assert after_restart.claim_next_delivery(now=NOW + timedelta(days=1)) is None


def test_independent_conversations_can_hold_delivery_claims(tmp_path: Path) -> None:
    store = _store(tmp_path / "independent.db")
    _, first = _pending_completion(store, _message("SM-a", "customer-a"), now=NOW)
    _, second = _pending_completion(
        store,
        _message("SM-b", "customer-b"),
        now=NOW + timedelta(seconds=2),
    )

    first_claim = store.claim_next_delivery(now=NOW + timedelta(seconds=4))
    second_claim = store.claim_next_delivery(now=NOW + timedelta(seconds=4))

    assert first_claim is not None
    assert second_claim is not None
    assert {first_claim.delivery_id, second_claim.delivery_id} == {
        first.delivery_id,
        second.delivery_id,
    }


def test_independent_runners_do_not_hold_sqlite_transaction_during_send(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "parallel-senders.db"
    store = _store(database_path)
    _pending_completion(store, _message("SM-a", "customer-a"), now=NOW)
    _pending_completion(
        store,
        _message("SM-b", "customer-b"),
        now=NOW + timedelta(seconds=1),
    )
    barrier = Barrier(2)

    class BarrierSender(OutboundMessageSender):
        def __init__(self, provider_message_id: str) -> None:
            self.provider_message_id = provider_message_id

        def send(
            self,
            message: OutboundMessage,
            *,
            timeout_seconds: float,
        ) -> ProviderAcceptance:
            del message, timeout_seconds
            barrier.wait(timeout=2)
            return ProviderAcceptance(self.provider_message_id)

    runners = [
        OutboundDeliveryRunner(
            store=SqliteConversationStore(database_path),
            sender=BarrierSender("PM-a"),
            timeout_seconds=1.0,
        ),
        OutboundDeliveryRunner(
            store=SqliteConversationStore(database_path),
            sender=BarrierSender("PM-b"),
            timeout_seconds=1.0,
        ),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda runner: runner.run_once(now=NOW + timedelta(seconds=2)),
                runners,
            )
        )

    assert all(result is not None for result in results)
    assert {result.state for result in results if result is not None} == {DeliveryState.ACCEPTED}


@pytest.mark.parametrize(
    ("outcome", "expected_state", "expected_error"),
    [
        (ProviderAcceptance("PM-accepted"), DeliveryState.ACCEPTED, None),
        (
            OutboundRetryableError("proved non-acceptance"),
            DeliveryState.RETRYABLE,
            "provider_retryable",
        ),
        (
            OutboundPermanentError("definitive rejection"),
            DeliveryState.FAILED,
            "provider_permanent",
        ),
        (
            OutboundOutcomeUnknown("ambiguous submission"),
            DeliveryState.UNKNOWN,
            "provider_outcome_unknown",
        ),
    ],
)
def test_runner_persists_canonical_sender_outcomes(
    tmp_path: Path,
    outcome: ProviderAcceptance | Exception,
    expected_state: DeliveryState,
    expected_error: str | None,
) -> None:
    store = _store(tmp_path / f"runner-{expected_state}.db")
    _, delivery = _pending_completion(store)
    sender = DeterministicFakeOutboundSender(outcomes=[outcome])
    runner = OutboundDeliveryRunner(store=store, sender=sender, timeout_seconds=2.5)

    result = runner.run_once(now=NOW + timedelta(seconds=2))

    assert result is not None
    assert result.delivery_id == delivery.delivery_id
    assert result.state is expected_state
    assert result.safe_error_code == expected_error
    assert result.provider_message_id == (
        "PM-accepted" if expected_state is DeliveryState.ACCEPTED else None
    )
    assert len(sender.calls) == 1
    assert sender.calls[0][0].recipient_address == "customer-1"
    assert sender.calls[0][0].body == "Resposta persistida"
    assert sender.calls[0][1] == 2.5


@pytest.mark.parametrize(
    "terminal_state",
    [DeliveryState.ACCEPTED, DeliveryState.UNKNOWN, DeliveryState.FAILED],
)
def test_runner_does_not_reprocess_noneligible_delivery(
    tmp_path: Path,
    terminal_state: DeliveryState,
) -> None:
    store = _store(tmp_path / f"terminal-{terminal_state}.db")
    _pending_completion(store)
    if terminal_state is DeliveryState.ACCEPTED:
        outcome: ProviderAcceptance | Exception = ProviderAcceptance("PM-terminal")
    elif terminal_state is DeliveryState.UNKNOWN:
        outcome = OutboundOutcomeUnknown("ambiguous")
    else:
        outcome = OutboundPermanentError("rejected")
    sender = DeterministicFakeOutboundSender(outcomes=[outcome])
    runner = OutboundDeliveryRunner(store=store, sender=sender, timeout_seconds=1.0)
    first = runner.run_once(now=NOW + timedelta(seconds=2))

    second = runner.run_once(now=NOW + timedelta(days=1))

    assert first is not None
    assert first.state is terminal_state
    assert second is None
    assert len(sender.calls) == 1


def test_retryable_delivery_can_be_claimed_again_with_incremented_attempt(tmp_path: Path) -> None:
    store = _store(tmp_path / "retryable.db")
    _pending_completion(store)
    sender = DeterministicFakeOutboundSender(
        outcomes=[
            OutboundRetryableError("proved non-acceptance"),
            ProviderAcceptance("PM-retried"),
        ]
    )
    runner = OutboundDeliveryRunner(store=store, sender=sender, timeout_seconds=1.0)

    first = runner.run_once(now=NOW + timedelta(seconds=2))
    second = runner.run_once(now=NOW + timedelta(seconds=3))

    assert first is not None
    assert first.state is DeliveryState.RETRYABLE
    assert second is not None
    assert second.state is DeliveryState.ACCEPTED
    assert second.attempt_count == 2


def test_acceptance_then_local_failure_becomes_unknown_after_lease_expiry(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "acceptance-crash.db"
    store = _store(database_path)
    _, delivery = _pending_completion(store)
    sender = DeterministicFakeOutboundSender(
        outcomes=[ProviderAcceptance("PM-accepted-before-crash")]
    )

    class FinalizationCrashStore(SqliteConversationStore):
        def finalize_delivery(self, **_: object) -> bool:
            raise PersistenceUnavailable("synthetic crash before acceptance commit")

    runner = OutboundDeliveryRunner(
        store=FinalizationCrashStore(database_path),
        sender=sender,
        timeout_seconds=1.0,
    )
    with pytest.raises(PersistenceUnavailable, match="synthetic crash"):
        runner.run_once(now=NOW + timedelta(seconds=2))

    persisted = SqliteConversationStore(database_path).get_delivery(delivery.delivery_id)
    assert persisted is not None
    assert persisted.state is DeliveryState.SENDING
    assert (
        SqliteConversationStore(database_path).claim_next_delivery(now=NOW + timedelta(seconds=33))
        is None
    )
    ambiguous = SqliteConversationStore(database_path).get_delivery(delivery.delivery_id)
    assert ambiguous is not None
    assert ambiguous.state is DeliveryState.UNKNOWN
    assert ambiguous.provider_message_id is None


def test_provider_message_id_is_unique_per_provider(tmp_path: Path) -> None:
    store = _store(tmp_path / "provider-id.db")
    _pending_completion(store, _message("SM-a", "customer-a"), now=NOW)
    _pending_completion(
        store,
        _message("SM-b", "customer-b"),
        now=NOW + timedelta(seconds=2),
    )
    first = store.claim_next_delivery(now=NOW + timedelta(seconds=4))
    assert first is not None
    assert first.owner_token is not None
    assert store.finalize_delivery(
        delivery_id=first.delivery_id,
        owner_token=first.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="PM-duplicate",
        now=NOW + timedelta(seconds=5),
    )
    second = store.claim_next_delivery(now=NOW + timedelta(seconds=6))
    assert second is not None
    assert second.owner_token is not None

    with pytest.raises(PersistenceUnavailable):
        store.finalize_delivery(
            delivery_id=second.delivery_id,
            owner_token=second.owner_token,
            outcome=DeliveryState.ACCEPTED,
            provider_message_id="PM-duplicate",
            now=NOW + timedelta(seconds=7),
        )

    persisted_second = store.get_delivery(second.delivery_id)
    assert persisted_second is not None
    assert persisted_second.state is DeliveryState.SENDING


@pytest.mark.parametrize(
    "resolution",
    [DeliveryState.ACCEPTED_LEGACY, DeliveryState.CANCELLED],
)
def test_legacy_unverified_delivery_requires_explicit_reconciliation(
    tmp_path: Path,
    resolution: DeliveryState,
) -> None:
    store = _store(tmp_path / f"reconcile-{resolution}.db")
    claim = store.claim_generation(_message(), now=NOW)
    assert claim.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta sem evidência",
        delivery_state=DeliveryState.UNKNOWN,
        now=NOW + timedelta(seconds=1),
    )
    delivery = store.get_delivery_for_inbound(claim.inbound_message_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.UNKNOWN
    assert delivery.safe_error_code == "legacy_unverified"
    assert store.claim_next_delivery(now=NOW + timedelta(days=1)) is None

    assert store.reconcile_legacy_delivery(
        delivery_id=delivery.delivery_id,
        resolution=resolution,
        now=NOW + timedelta(days=1),
    )
    reconciled = store.get_delivery(delivery.delivery_id)

    assert reconciled is not None
    assert reconciled.state is resolution
    assert not store.reconcile_legacy_delivery(
        delivery_id=delivery.delivery_id,
        resolution=resolution,
        now=NOW + timedelta(days=2),
    )
    later = store.claim_generation(
        _message("SM-after-reconciliation"),
        now=NOW + timedelta(days=3),
    )
    assert later.acquired


def test_provider_unknown_cannot_use_legacy_reconciliation(tmp_path: Path) -> None:
    store = _store(tmp_path / "provider-unknown.db")
    _, delivery = _pending_completion(store)
    runner = OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[OutboundOutcomeUnknown("ambiguous")]),
        timeout_seconds=1.0,
    )
    result = runner.run_once(now=NOW + timedelta(seconds=2))
    assert result is not None
    assert result.state is DeliveryState.UNKNOWN

    assert not store.reconcile_legacy_delivery(
        delivery_id=delivery.delivery_id,
        resolution=DeliveryState.ACCEPTED_LEGACY,
        now=NOW + timedelta(seconds=3),
    )


def test_retention_cannot_remove_nonterminal_delivery_or_linked_messages(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "retention.db")
    claim, delivery = _pending_completion(store, now=NOW - timedelta(days=100))

    with pytest.raises(PersistenceUnavailable):
        store.purge_messages_older_than(NOW - timedelta(days=90))

    assert store.get_delivery(delivery.delivery_id) is not None
    generation = store.get_generation(
        provider=_message().provider,
        provider_message_id=_message().provider_message_id,
    )
    assert generation is not None
    assert generation.inbound_message_id == claim.inbound_message_id


def test_retention_atomically_removes_terminal_delivery_and_linked_messages(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "terminal-retention.db"
    store = _store(database_path)
    _, delivery = _pending_completion(store, now=NOW - timedelta(days=100))
    accepted = OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-retention")]),
        timeout_seconds=1.0,
    ).run_once(now=NOW - timedelta(days=100) + timedelta(seconds=2))
    assert accepted is not None

    result = store.purge_messages_older_than(NOW - timedelta(days=90))

    assert result.messages_deleted == 2
    assert result.conversations_deleted == 1
    assert store.get_delivery(delivery.delivery_id) is None
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone()[0] == 0


def test_retention_preserves_failed_delivery_that_blocks_a_later_message(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "failed-retention-barrier.db"
    store = _store(database_path)
    _pending_completion(store, now=NOW - timedelta(days=100))
    failed = OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(
            outcomes=[OutboundPermanentError("definitive rejection")]
        ),
        timeout_seconds=1.0,
    ).run_once(now=NOW - timedelta(days=100) + timedelta(seconds=2))
    assert failed is not None
    later_message = _message("SM-later")
    later = store.admit_generation(later_message, now=NOW)
    assert later.blocked_by_predecessor is False
    blocked = store.claim_generation(later_message, now=NOW)
    assert blocked.blocked_by_predecessor

    with pytest.raises(PersistenceUnavailable):
        store.purge_messages_older_than(NOW - timedelta(days=90))

    still_blocked = store.claim_generation(later_message, now=NOW + timedelta(days=1))
    assert still_blocked.blocked_by_predecessor
    assert store.get_delivery(failed.delivery_id) is not None
