import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest

from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import GenerationMetric
from rj_studio_ai.persistence import (
    GenerationClaimResult,
    GenerationMetricRecord,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def _message(provider_message_id: str = "SM-generation") -> InboundMessage:
    return InboundMessage(
        provider="twilio",
        provider_message_id=provider_message_id,
        customer_address="whatsapp:+5511000000000",
        recipient_address="whatsapp:+14155238886",
        body="Mensagem sintética",
    )


def _store(database_path: Path) -> SqliteConversationStore:
    store = SqliteConversationStore(database_path)
    store.initialize()
    return store


def test_claim_is_durable_until_lease_expiry_and_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "claims.db"
    first_process = _store(database_path)

    first = first_process.claim_generation(
        _message(),
        now=NOW,
    )
    before_expiry = SqliteConversationStore(database_path).claim_generation(
        _message(),
        now=NOW + timedelta(seconds=29),
    )
    after_expiry = SqliteConversationStore(database_path).claim_generation(
        _message(),
        now=NOW + timedelta(seconds=30),
    )

    assert first.acquired
    assert first.state is GenerationState.PROCESSING
    assert first.attempt_count == 1
    assert first.owner_token is not None
    assert first.lease_expires_at == NOW + timedelta(seconds=30)
    assert not before_expiry.acquired
    assert before_expiry.owner_token is None
    assert before_expiry.attempt_count == 1
    assert after_expiry.acquired
    assert after_expiry.owner_token is not None
    assert after_expiry.owner_token != first.owner_token
    assert after_expiry.attempt_count == 2


def test_generation_metric_persists_without_message_content(tmp_path: Path) -> None:
    store = _store(tmp_path / "metrics.db")
    claim = store.claim_generation(_message(), now=NOW)

    store.record_generation_metric(
        inbound_message_id=claim.inbound_message_id,
        attempt_number=claim.attempt_count,
        metric=GenerationMetric(
            provider="anthropic",
            model="claude-sonnet-5",
            configuration="thinking=disabled;format=json_schema;max_tokens=240",
            latency_ms=420,
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
            estimated_cost_microusd=675,
            outcome="success",
            error_code=None,
        ),
        now=NOW,
    )

    metrics = store.get_generation_metrics(inbound_message_id=claim.inbound_message_id)

    assert metrics == [
        GenerationMetricRecord(
            attempt_number=1,
            provider="anthropic",
            model="claude-sonnet-5",
            configuration="thinking=disabled;format=json_schema;max_tokens=240",
            latency_ms=420,
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
            estimated_cost_microusd=675,
            outcome="success",
            error_code=None,
        )
    ]


def test_concurrent_claims_for_one_inbound_have_one_owner(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent.db"
    _store(database_path)
    attempts = 8
    barrier = Barrier(attempts)

    def claim(_: int) -> bool:
        barrier.wait()
        result = SqliteConversationStore(database_path).claim_generation(
            _message(),
            now=NOW,
        )
        return result.acquired

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        acquired = list(executor.map(claim, range(attempts)))

    assert acquired.count(True) == 1
    assert acquired.count(False) == attempts - 1


def test_wrong_or_stale_owner_cannot_complete_generation(tmp_path: Path) -> None:
    database_path = tmp_path / "ownership.db"
    store = _store(database_path)
    first = store.claim_generation(_message(), now=NOW)
    assert first.owner_token is not None

    wrong_owner_completed = store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token="not-the-owner",
        reply_body="Resposta incorreta",
        now=NOW + timedelta(seconds=1),
    )
    current = store.claim_generation(
        _message(),
        now=NOW + timedelta(seconds=30),
    )
    assert current.owner_token is not None
    stale_owner_completed = store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta obsoleta",
        now=NOW + timedelta(seconds=31),
    )
    current_owner_completed = store.complete_generation(
        inbound_message_id=current.inbound_message_id,
        owner_token=current.owner_token,
        reply_body="Resposta válida",
        now=NOW + timedelta(seconds=31),
    )

    assert not wrong_owner_completed
    assert current.acquired
    assert not stale_owner_completed
    assert current_owner_completed
    assert [
        (item.direction, item.body)
        for item in store.get_history(
            provider="twilio",
            customer_address=_message().customer_address,
        )
    ] == [
        ("inbound", "Mensagem sintética"),
        ("outbound", "Resposta válida"),
    ]


def test_retryable_claim_has_at_most_two_attempts(tmp_path: Path) -> None:
    store = _store(tmp_path / "retryable.db")
    first = store.claim_generation(_message(), now=NOW)
    assert first.owner_token is not None

    assert store.mark_generation_retryable(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        now=NOW + timedelta(seconds=1),
    )
    second = store.claim_generation(
        _message(),
        now=NOW + timedelta(seconds=2),
    )
    assert second.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=second.inbound_message_id,
        owner_token=second.owner_token,
        now=NOW + timedelta(seconds=3),
    )
    exhausted = store.claim_generation(
        _message(),
        now=NOW + timedelta(seconds=4),
    )

    assert second.acquired
    assert second.attempt_count == 2
    assert not exhausted.acquired
    assert exhausted.state is GenerationState.RETRYABLE
    assert exhausted.attempt_count == 2
    assert exhausted.owner_token is None
    finalization = store.claim_exhausted_finalization(
        inbound_message_id=exhausted.inbound_message_id,
        now=NOW + timedelta(seconds=5),
    )
    assert finalization.acquired
    assert finalization.owner_token is not None
    assert finalization.attempt_count == 2
    assert store.complete_generation(
        inbound_message_id=finalization.inbound_message_id,
        owner_token=finalization.owner_token,
        reply_body="Vou chamar uma pessoa da equipe para continuar com você.",
        now=NOW + timedelta(seconds=6),
    )
    terminal = store.get_generation(
        provider="twilio",
        provider_message_id=_message().provider_message_id,
    )
    assert terminal is not None
    assert terminal.state is GenerationState.COMPLETED
    assert terminal.attempt_count == 2


def test_exhausted_generation_can_be_completed_safely_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "exhausted.db"
    first_process = _store(database_path)
    first = first_process.claim_generation(_message(), now=NOW)
    second = first_process.claim_generation(
        _message(),
        now=NOW + timedelta(seconds=30),
    )
    assert first.owner_token is not None
    assert second.owner_token is not None

    before_expiry = SqliteConversationStore(database_path).claim_exhausted_finalization(
        inbound_message_id=second.inbound_message_id,
        now=NOW + timedelta(seconds=59),
    )
    finalization = SqliteConversationStore(database_path).claim_exhausted_finalization(
        inbound_message_id=second.inbound_message_id,
        now=NOW + timedelta(seconds=60),
    )
    assert finalization.owner_token is not None
    completed = SqliteConversationStore(database_path).complete_generation(
        inbound_message_id=finalization.inbound_message_id,
        owner_token=finalization.owner_token,
        reply_body="Vou chamar uma pessoa da equipe para continuar com você.",
        now=NOW + timedelta(seconds=61),
    )
    replay = SqliteConversationStore(database_path).claim_generation(
        _message(),
        now=NOW + timedelta(days=1),
    )

    assert not before_expiry.acquired
    assert before_expiry.state is GenerationState.PROCESSING
    assert before_expiry.owner_token is None
    assert finalization.acquired
    assert completed
    assert not replay.acquired
    assert replay.state is GenerationState.COMPLETED
    assert replay.attempt_count == 2
    assert replay.reply_body == "Vou chamar uma pessoa da equipe para continuar com você."
    assert not SqliteConversationStore(database_path).complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=second.owner_token,
        reply_body="Resposta obsoleta",
        now=NOW + timedelta(days=1),
    )


def test_concurrent_exhausted_finalization_has_one_owner(tmp_path: Path) -> None:
    database_path = tmp_path / "concurrent-exhausted.db"
    store = _store(database_path)
    first = store.claim_generation(_message(), now=NOW)
    assert first.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        now=NOW + timedelta(seconds=1),
    )
    second = store.claim_generation(_message(), now=NOW + timedelta(seconds=2))
    assert second.owner_token is not None
    assert store.mark_generation_retryable(
        inbound_message_id=second.inbound_message_id,
        owner_token=second.owner_token,
        now=NOW + timedelta(seconds=3),
    )
    barrier = Barrier(2)

    def claim_finalization(_: int) -> GenerationClaimResult:
        barrier.wait()
        return SqliteConversationStore(database_path).claim_exhausted_finalization(
            inbound_message_id=second.inbound_message_id,
            now=NOW + timedelta(seconds=4),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim_finalization, range(2)))

    owner = next(claim for claim in claims if claim.acquired)
    assert owner.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=owner.inbound_message_id,
        owner_token=owner.owner_token,
        reply_body="Resposta segura",
        now=NOW + timedelta(seconds=5),
    )

    assert sum(claim.acquired for claim in claims) == 1
    assert [
        (item.direction, item.body)
        for item in store.get_history(
            provider="twilio",
            customer_address=_message().customer_address,
        )
    ] == [
        ("inbound", "Mensagem sintética"),
        ("outbound", "Resposta segura"),
    ]


def test_completed_reply_is_terminal_and_replayed_after_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "completed.db"
    store = _store(database_path)
    claim = store.claim_generation(_message(), now=NOW)
    assert claim.owner_token is not None

    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta persistida",
        now=NOW + timedelta(seconds=1),
    )
    replay = SqliteConversationStore(database_path).claim_generation(
        replace(_message(), body="Corpo alterado em retry"),
        now=NOW + timedelta(days=1),
    )

    assert not replay.acquired
    assert replay.state is GenerationState.COMPLETED
    assert replay.reply_body == "Resposta persistida"
    assert replay.owner_token is None


def test_suppressed_inbound_is_terminal_without_reply(tmp_path: Path) -> None:
    database_path = tmp_path / "suppressed.db"
    store = _store(database_path)

    suppressed = store.suppress_generation(_message(), now=NOW)
    after_restart = SqliteConversationStore(database_path).claim_generation(
        _message(),
        now=NOW + timedelta(days=1),
    )

    assert suppressed.state is GenerationState.SUPPRESSED
    assert suppressed.attempt_count == 0
    assert not after_restart.acquired
    assert after_restart.state is GenerationState.SUPPRESSED
    assert after_restart.reply_body is None
    assert [
        (item.direction, item.body)
        for item in store.get_history(
            provider="twilio",
            customer_address=_message().customer_address,
        )
    ] == [("inbound", "Mensagem sintética")]


def test_legacy_reply_path_cannot_overwrite_suppressed_state(tmp_path: Path) -> None:
    store = _store(tmp_path / "suppressed-legacy.db")
    store.suppress_generation(_message(), now=NOW)

    with pytest.raises(PersistenceUnavailable):
        store.get_or_create_reply(_message(), "Resposta indevida")

    record = store.get_generation(
        provider="twilio",
        provider_message_id=_message().provider_message_id,
    )
    assert record is not None
    assert record.state is GenerationState.SUPPRESSED
    assert (
        len(
            store.get_history(
                provider="twilio",
                customer_address=_message().customer_address,
            )
        )
        == 1
    )


def test_failed_completion_rolls_back_reply_and_state(tmp_path: Path) -> None:
    database_path = tmp_path / "rollback.db"
    store = _store(database_path)
    claim = store.claim_generation(_message(), now=NOW)
    assert claim.owner_token is not None
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_generation_completion
            BEFORE UPDATE OF state ON message_processing
            WHEN NEW.state = 'completed'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic completion failure');
            END
            """
        )

    with pytest.raises(PersistenceUnavailable, match="persistence is unavailable"):
        store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Resposta parcial",
            now=NOW + timedelta(seconds=1),
        )

    record = store.get_generation(
        provider="twilio",
        provider_message_id=_message().provider_message_id,
    )
    assert record is not None
    assert record.state is GenerationState.PROCESSING
    assert (
        store.get_history(
            provider="twilio",
            customer_address=_message().customer_address,
        )[0].direction
        == "inbound"
    )
    assert (
        len(
            store.get_history(
                provider="twilio",
                customer_address=_message().customer_address,
            )
        )
        == 1
    )
