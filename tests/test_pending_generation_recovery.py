from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import GeneratedReply, GenerationFailure, GenerationTimeout
from rj_studio_ai.main import create_app
from rj_studio_ai.maintenance import main as maintenance_main
from rj_studio_ai.persistence import GenerationState, SqliteConversationStore
from rj_studio_ai.recovery import PendingGenerationRecovery, RecoveryBlocked, RecoveryNotAvailable


class RecordingGenerator:
    def __init__(self, replies: list[str | Exception] | None = None) -> None:
        self._replies = iter(replies or ["Resposta recuperada"])
        self.messages: list[InboundMessage] = []

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        del remaining_budget
        self.messages.append(message)
        reply = next(self._replies)
        if isinstance(reply, Exception):
            raise reply
        return GeneratedReply.from_reply_text(reply)

    def is_configured(self) -> bool:
        return True


class UnavailableGenerator:
    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        del message, remaining_budget
        raise GenerationFailure("provider_unavailable")

    def is_configured(self) -> bool:
        return True


def _message(
    message_id: str,
    *,
    customer: str = "customer-1",
    body: str = "Mensagem sintética",
) -> InboundMessage:
    return InboundMessage(
        provider="test-provider",
        provider_message_id=message_id,
        customer_address=customer,
        recipient_address="studio-1",
        body=body,
    )


def _store(database_path: Path) -> SqliteConversationStore:
    store = SqliteConversationStore(database_path)
    store.initialize()
    return store


def _recovery(
    store: SqliteConversationStore, generator: RecordingGenerator
) -> PendingGenerationRecovery:
    return PendingGenerationRecovery(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=generator,
            safe_failure_reply="Resposta segura",
        ),
    )


def test_lists_retryable_and_stale_pending_messages_without_active_or_terminal_work(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "pending.db")
    retryable = store.admit_generation(_message("retryable", customer="retryable-customer"))
    stale = store.claim_generation(
        _message("stale", customer="stale-customer"), now=datetime.now(UTC) - timedelta(minutes=1)
    )
    active = store.claim_generation(_message("active", customer="active-customer"))
    completed = store.claim_generation(_message("completed", customer="completed-customer"))
    suppressed = store.suppress_generation(_message("suppressed", customer="suppressed-customer"))
    assert completed.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=completed.inbound_message_id,
        owner_token=completed.owner_token,
        reply_body="Resposta terminal",
    )
    assert stale.owner_token is not None
    assert active.owner_token is not None

    candidates = PendingGenerationRecovery(
        store=SqliteConversationStore(tmp_path / "pending.db"),
        responder=MessageResponder(
            store=SqliteConversationStore(tmp_path / "pending.db"),
            generator=RecordingGenerator(),
            safe_failure_reply="Resposta segura",
        ),
    ).list_pending()

    assert [
        (candidate.inbound_message_id, candidate.state, candidate.is_stale)
        for candidate in candidates
    ] == [
        (retryable.inbound_message_id, GenerationState.RETRYABLE, False),
        (stale.inbound_message_id, GenerationState.PROCESSING, True),
    ]
    assert all(
        candidate.inbound_message_id
        not in {
            active.inbound_message_id,
            completed.inbound_message_id,
            suppressed.inbound_message_id,
        }
        for candidate in candidates
    )


def test_manual_recovery_uses_the_normal_claim_and_generation_flow(tmp_path: Path) -> None:
    store = _store(tmp_path / "recover.db")
    pending = store.admit_generation(_message("pending"))
    generator = RecordingGenerator(["Resposta recuperada"])

    result = _recovery(store, generator).recover(pending.inbound_message_id)

    assert result.inbound_message_id == pending.inbound_message_id
    assert result.state is GenerationState.COMPLETED
    assert result.reply_persisted
    assert [message.recipient_address for message in generator.messages] == ["studio-1"]
    replay = store.get_generation(provider="test-provider", provider_message_id="pending")
    assert replay is not None
    assert replay.reply_body == "Resposta recuperada"
    assert len(store.get_history(provider="test-provider", customer_address="customer-1")) == 2


def test_recovery_does_not_bypass_a_nonterminal_predecessor(tmp_path: Path) -> None:
    store = _store(tmp_path / "ordered-recovery.db")
    first = store.admit_generation(_message("first"))
    second = store.admit_generation(_message("second"))
    generator = RecordingGenerator(["Resposta da primeira", "Resposta da segunda"])
    recovery = _recovery(store, generator)

    candidates = recovery.list_pending()
    second_candidate = next(
        item for item in candidates if item.inbound_message_id == second.inbound_message_id
    )
    assert second_candidate.blocked_by_predecessor
    with pytest.raises(RecoveryBlocked):
        recovery.recover(second.inbound_message_id)

    assert recovery.recover(first.inbound_message_id).state is GenerationState.COMPLETED
    assert recovery.recover(second.inbound_message_id).state is GenerationState.COMPLETED
    assert [message.provider_message_id for message in generator.messages] == ["first", "second"]


def test_recovery_in_one_conversation_does_not_block_another_conversation(tmp_path: Path) -> None:
    store = _store(tmp_path / "independent-recovery.db")
    store.admit_generation(_message("first", customer="customer-1"))
    independent = store.admit_generation(_message("independent", customer="customer-2"))
    generator = RecordingGenerator(["Resposta independente"])

    result = _recovery(store, generator).recover(independent.inbound_message_id)

    assert result.state is GenerationState.COMPLETED
    assert [message.provider_message_id for message in generator.messages] == ["independent"]
    first_lifecycle = store.get_generation(provider="test-provider", provider_message_id="first")
    assert first_lifecycle is not None
    assert first_lifecycle.state is GenerationState.RETRYABLE


def test_recovery_rejects_active_terminal_and_replayed_work_without_duplicate_reply(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "protected-recovery.db")
    active = store.claim_generation(_message("active", customer="active-customer"))
    completed = store.claim_generation(_message("completed", customer="completed-customer"))
    suppressed = store.suppress_generation(_message("suppressed", customer="suppressed-customer"))
    assert active.owner_token is not None
    assert completed.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=completed.inbound_message_id,
        owner_token=completed.owner_token,
        reply_body="Resposta persistida",
    )
    recovery = _recovery(store, RecordingGenerator())

    for inbound_message_id in (
        active.inbound_message_id,
        completed.inbound_message_id,
        suppressed.inbound_message_id,
    ):
        with pytest.raises(RecoveryNotAvailable):
            recovery.recover(inbound_message_id)

    assert (
        len(store.get_history(provider="test-provider", customer_address="completed-customer")) == 2
    )


def test_stale_processing_recovery_and_llm_timeout_follow_the_normal_safe_lifecycle(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "stale-recovery.db")
    stale = store.claim_generation(_message("stale"), now=datetime.now(UTC) - timedelta(minutes=1))
    assert stale.owner_token is not None
    generator = RecordingGenerator(
        [GenerationTimeout("provider_timeout"), GenerationTimeout("provider_timeout")]
    )

    result = _recovery(store, generator).recover(stale.inbound_message_id)

    assert result.state is GenerationState.COMPLETED
    lifecycle = store.get_generation(provider="test-provider", provider_message_id="stale")
    assert lifecycle is not None
    assert lifecycle.attempt_count == 2
    assert lifecycle.reply_body == "Resposta segura"
    assert len(store.get_history(provider="test-provider", customer_address="customer-1")) == 2


def test_webhook_retry_exhaustion_survives_restart_then_manual_recovery(tmp_path: Path) -> None:
    database_path = tmp_path / "restart-recovery.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta segura",
            twilio_validate_signature=False,
        ),
        generator=UnavailableGenerator(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            data={
                "MessageSid": "restart-message",
                "From": "customer-restart",
                "To": "studio-restart",
                "Body": "Mensagem antes do restart",
            },
        )

    assert response.status_code == 503
    restarted_store = SqliteConversationStore(database_path)
    recovery = _recovery(restarted_store, RecordingGenerator(["Resposta após restart"]))
    candidates = recovery.list_pending()
    assert len(candidates) == 1

    result = recovery.recover(candidates[0].inbound_message_id)

    assert result.state is GenerationState.COMPLETED
    lifecycle = restarted_store.get_generation(
        provider="twilio", provider_message_id="restart-message"
    )
    assert lifecycle is not None
    assert lifecycle.attempt_count == 2
    assert lifecycle.reply_body == "Resposta após restart"
    assert (
        len(restarted_store.get_history(provider="twilio", customer_address="customer-restart"))
        == 2
    )


def test_recovery_cannot_preempt_a_new_owner_after_a_stale_claim_is_reacquired(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "stale-owner-recovery.db")
    message = _message("stale-owner")
    first = store.claim_generation(message, now=datetime.now(UTC) - timedelta(minutes=1))
    assert first.owner_token is not None
    current = store.claim_generation(message)
    assert current.owner_token is not None
    assert current.owner_token != first.owner_token

    with pytest.raises(RecoveryNotAvailable):
        _recovery(store, RecordingGenerator()).recover(first.inbound_message_id)

    assert not store.complete_generation(
        inbound_message_id=first.inbound_message_id,
        owner_token=first.owner_token,
        reply_body="Resposta obsoleta",
    )
    lifecycle = store.get_generation(provider="test-provider", provider_message_id="stale-owner")
    assert lifecycle is not None
    assert lifecycle.state is GenerationState.PROCESSING


def test_maintenance_commands_list_redacted_work_and_recover_one_message(
    tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "maintenance-recovery.db"
    store = _store(database_path)
    pending = store.admit_generation(
        _message("pending", customer="customer-private", body="body-private")
    )

    listed = maintenance_main(["--database-path", str(database_path), "list-pending-generations"])
    listed_output = capsys.readouterr().out
    recovered = maintenance_main(
        [
            "--database-path",
            str(database_path),
            "recover-generation",
            "--inbound-message-id",
            str(pending.inbound_message_id),
        ]
    )
    recovered_output = capsys.readouterr().out

    assert listed == 0
    assert f"inbound_message_id={pending.inbound_message_id}" in listed_output
    assert "customer-private" not in listed_output
    assert "body-private" not in listed_output
    assert recovered == 0
    assert (
        recovered_output == f"Recovery completed inbound_message_id={pending.inbound_message_id}.\n"
    )
