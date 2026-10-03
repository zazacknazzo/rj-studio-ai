import hashlib
import hmac
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from rj_studio_ai import maintenance
from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import (
    AIReply,
    DeliveryStatus,
    DeliveryStatusReceived,
    InboundMessage,
    InboundMessageReceived,
    ProviderWebhookEventBatch,
)
from rj_studio_ai.generation import GeneratedReply, GenerationFailure
from rj_studio_ai.llm_decision import LLMDecision
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.processing import ProcessingRunner
from rj_studio_ai.providers.base import (
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
    ProviderWebhookResponse,
    WhatsAppProvider,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender


def _message(identifier="inbound-1", body="Preciso falar com uma pessoa", customer="customer"):
    return InboundMessage("test-provider", identifier, customer, "studio", body)


def _activate(store, message=None, now=None):
    claim = store.claim_generation(message or _message(), now=now)
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Vou pedir ajuda à equipe pra seguir com segurança.",
        delivery_state=DeliveryState.PENDING,
        handoff_reason="explicit_human_request",
        now=now,
    )
    return claim, store.list_active_handoffs()[0]


def test_owned_completion_activates_durable_conversation_handoff_and_suppresses_future(tmp_path):
    path = tmp_path / "handoff.db"
    store = SqliteConversationStore(path)
    store.initialize()
    claim = store.claim_generation(_message())
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Vou pedir ajuda à equipe pra seguir com segurança.",
        delivery_state=DeliveryState.PENDING,
        handoff_reason="explicit_human_request",
    )

    handoff = store.list_active_handoffs()[0]
    assert handoff.reason_code == "explicit_human_request"
    delivery = store.get_delivery_for_inbound(claim.inbound_message_id)
    assert delivery.handoff_token == handoff.owner_token
    assert delivery.state is DeliveryState.PENDING
    reopened = SqliteConversationStore(path)
    second = reopened.admit_generation(_message("inbound-2"))
    assert second.state is GenerationState.SUPPRESSED
    assert not second.acquired and second.reply_body is None
    assert reopened.list_active_handoffs() == [handoff]
    assert len(reopened.get_history(provider="test-provider", customer_address="customer")) == 3


def test_release_is_fenced_and_only_future_inbounds_can_resume(tmp_path):
    store = SqliteConversationStore(tmp_path / "release.db")
    store.initialize()
    claim, handoff = _activate(store)
    suppressed = store.admit_generation(_message("inbound-2"))
    assert not store.release_handoff(conversation_id=handoff.conversation_id, owner_token="wrong")
    assert store.list_active_handoffs() == [handoff]
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
    )
    assert not store.list_active_handoffs()
    assert store.get_delivery_for_inbound(claim.inbound_message_id).state is DeliveryState.CANCELLED
    assert not store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="stale",
    )
    assert store.claim_generation(_message("inbound-2")).state is GenerationState.SUPPRESSED
    assert store.get_delivery_for_inbound(suppressed.inbound_message_id) is None
    assert store.claim_generation(_message("inbound-3")).acquired


def test_reactivation_rejects_release_of_previous_episode(tmp_path):
    store = SqliteConversationStore(tmp_path / "reactivate.db")
    store.initialize()
    _, first = _activate(store)
    assert store.release_handoff(
        conversation_id=first.conversation_id, owner_token=first.owner_token
    )
    _, second = _activate(store, _message("inbound-2"))
    assert second.owner_token != first.owner_token
    assert not store.release_handoff(
        conversation_id=first.conversation_id, owner_token=first.owner_token
    )
    assert store.list_active_handoffs() == [second]


class Model:
    def __init__(self, handoff=False, reason=None):
        self.calls = 0
        self.handoff = handoff
        self.reason = reason

    def generate(self, *args, **kwargs):
        self.calls += 1
        return GeneratedReply(
            decision=LLMDecision.model_validate(
                {
                    "intents": ["greeting"],
                    "reply_text": "Texto não confiável",
                    "reply_parts": [{"kind": "phrase", "phrase": "help"}],
                    "knowledge_refs": [],
                    "critical_claims": [],
                    "uncertainty": "low",
                    "handoff": self.handoff,
                    "handoff_reason": self.reason,
                }
            )
        )

    def is_configured(self):
        return True


def _processing(store, model):
    return ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=model,
            safe_failure_reply="Resposta segura",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    )


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("Meu couro cabeludo está ardendo", "personalized_technical_risk"),
        ("Quero fazer uma reclamação séria", "relevant_complaint"),
    ],
)
def test_trusted_policy_activates_handoff_and_no_later_generation_runs(tmp_path, body, reason):
    store = SqliteConversationStore(tmp_path / "runtime.db")
    store.initialize()
    model = Model()
    runner = _processing(store, model)
    store.admit_generation(_message(body=body))
    store.admit_generation(_message("inbound-2", body="Outra mensagem"))
    first = runner.run_once()
    assert first is not None
    assert store.list_active_handoffs()[0].reason_code == reason
    assert "equipe" in first.reply_body
    if reason == "personalized_technical_risk":
        assert "pare e procure avaliação profissional" in first.reply_body
        assert "atendimento médico urgente" in first.reply_body
    assert runner.run_once() is None
    assert model.calls == 1
    assert (
        store.get_generation(provider="test-provider", provider_message_id="inbound-2").state
        is GenerationState.SUPPRESSED
    )


def test_false_proposal_with_no_trusted_override_does_not_activate(tmp_path):
    store = SqliteConversationStore(tmp_path / "false.db")
    store.initialize()
    store.admit_generation(_message(body="Oi"))
    result = _processing(store, Model()).run_once()
    assert result.reply_body == "Como posso te ajudar?"
    assert not store.list_active_handoffs()


def test_untrusted_handoff_reason_is_not_persisted_or_echoed(tmp_path):
    store = SqliteConversationStore(tmp_path / "reason.db")
    store.initialize()
    store.admit_generation(_message(body="Preciso de avaliação"))
    result = _processing(store, Model(handoff=True, reason="sensitive-customer-detail")).run_once()
    handoff = store.list_active_handoffs()[0]
    assert handoff.reason_code == "model_requested_handoff"
    assert "sensitive" not in result.reply_body


def test_release_cancels_a_claim_that_has_not_started_submission(tmp_path):
    store = SqliteConversationStore(tmp_path / "before-send.db")
    store.initialize()
    _, handoff = _activate(store)
    claim = store.claim_next_delivery()
    assert claim is not None
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
    )
    assert store.get_delivery(claim.delivery_id).state is DeliveryState.CANCELLED
    assert not store.authorize_delivery_submission(
        delivery_id=claim.delivery_id, owner_token=claim.owner_token
    )
    assert store.claim_next_delivery() is None


def test_release_during_submission_cannot_recall_provider_acceptance(tmp_path):
    store = SqliteConversationStore(tmp_path / "in-flight.db")
    store.initialize()
    generation, handoff = _activate(store)

    class Sender:
        def send(self, message, *, timeout_seconds):
            assert store.release_handoff(
                conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
            )
            assert (
                store.get_delivery_for_inbound(generation.inbound_message_id).state
                is DeliveryState.SENDING
            )
            return ProviderAcceptance("outbound-accepted")

    result = OutboundDeliveryRunner(store=store, sender=Sender(), timeout_seconds=5).run_once()
    assert result.state is DeliveryState.ACCEPTED
    assert result.provider_message_id == "outbound-accepted"
    assert not store.list_active_handoffs()


class CanonicalProvider(WhatsAppProvider):
    def receive(self, webhook):
        payload = json.loads(webhook.body)
        return ProviderWebhookEventBatch(
            events=(
                InboundMessageReceived(
                    "test-provider",
                    payload["id"],
                    "customer",
                    "studio",
                    payload["body"],
                ),
            )
        )

    def acknowledge(self):
        return ProviderWebhookResponse(body="", media_type="text/plain")

    def render_legacy_reply(self, reply: AIReply):
        return ProviderWebhookResponse(body=reply.body, media_type="text/plain")

    def is_configured(self):
        return True


def test_legacy_webhook_acknowledges_suppressed_retry_after_release_and_restart(tmp_path):
    path = tmp_path / "http.db"
    model = Model()
    app = create_app(
        Settings(_env_file=None, database_path=path, delivery_mode="legacy"),
        provider=CanonicalProvider(),
        generator=model,
    )
    with TestClient(app) as client:
        first = client.post(
            "/webhooks/whatsapp", json={"id": "inbound-1", "body": "Quero falar com uma pessoa"}
        )
        assert first.status_code == 200 and "equipe" in first.text
        second = client.post("/webhooks/whatsapp", json={"id": "inbound-2", "body": "Continue"})
        assert second.status_code == 200 and second.text == ""
        store = SqliteConversationStore(path)
        handoff = store.list_active_handoffs()[0]
        assert store.release_handoff(
            conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
        )
    reopened_app = create_app(
        Settings(_env_file=None, database_path=path, delivery_mode="legacy"),
        provider=CanonicalProvider(),
        generator=model,
    )
    with TestClient(reopened_app) as client:
        replay = client.post("/webhooks/whatsapp", json={"id": "inbound-2", "body": "Changed body"})
        assert replay.status_code == 200 and replay.text == ""
        future = client.post("/webhooks/whatsapp", json={"id": "inbound-3", "body": "Oi"})
        assert future.status_code == 200 and future.text == "Como posso te ajudar?"
    assert model.calls == 2
    suppressed = store.get_generation(provider="test-provider", provider_message_id="inbound-2")
    assert suppressed.state is GenerationState.SUPPRESSED and suppressed.inbound_body == "Continue"


def test_legacy_replay_of_an_older_reply_is_ack_only_while_handoff_is_active(tmp_path):
    model = Model()
    app = create_app(
        Settings(_env_file=None, database_path=tmp_path / "legacy-old.db", delivery_mode="legacy"),
        provider=CanonicalProvider(),
        generator=model,
    )
    with TestClient(app) as client:
        assert (
            "Como posso"
            in client.post("/webhooks/whatsapp", json={"id": "hello", "body": "Oi"}).text
        )
        assert (
            "equipe"
            in client.post(
                "/webhooks/whatsapp", json={"id": "handoff", "body": "Quero falar com uma pessoa"}
            ).text
        )
        replay = client.post("/webhooks/whatsapp", json={"id": "hello", "body": "Oi"})
        assert replay.status_code == 200 and replay.text == ""
    assert model.calls == 2


@pytest.mark.parametrize(
    "boundary",
    [
        "BEFORE INSERT ON outbound_deliveries",
        "BEFORE UPDATE OF state ON message_processing WHEN NEW.state = 'completed'",
        "BEFORE INSERT ON conversation_handoffs",
        "AFTER INSERT ON conversation_handoffs",
    ],
)
def test_fault_rolls_back_reply_delivery_processing_and_handoff(tmp_path, boundary):
    path = tmp_path / "rollback.db"
    store = SqliteConversationStore(path)
    store.initialize()
    claim = store.claim_generation(_message())
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"CREATE TRIGGER injected_failure {boundary} "
            "BEGIN SELECT RAISE(ABORT, 'synthetic fault'); END"
        )
    with pytest.raises(PersistenceUnavailable):
        store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Vou pedir ajuda à equipe pra seguir com segurança.",
            delivery_state=DeliveryState.PENDING,
            handoff_reason="explicit_human_request",
        )
    state = store.get_generation(provider="test-provider", provider_message_id="inbound-1")
    assert state.state is GenerationState.PROCESSING and state.reply_body is None
    assert store.get_delivery_for_inbound(claim.inbound_message_id) is None
    assert not store.list_active_handoffs()
    assert len(store.get_history(provider="test-provider", customer_address="customer")) == 1


def test_concurrent_duplicate_activation_has_one_confirmation(tmp_path):
    store = SqliteConversationStore(tmp_path / "duplicate.db")
    store.initialize()
    claim = store.claim_generation(_message())
    gate = Barrier(2)

    def complete():
        gate.wait(timeout=3)
        return store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Vou pedir ajuda à equipe pra seguir com segurança.",
            delivery_state=DeliveryState.PENDING,
            handoff_reason="explicit_human_request",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: complete(), range(2)))
    assert sorted(results) == [False, True]
    assert len(store.list_active_handoffs()) == 1
    assert len(store.get_history(provider="test-provider", customer_address="customer")) == 2
    assert store.get_delivery_for_inbound(claim.inbound_message_id) is not None


def test_stale_generation_cannot_complete_or_reactivate_during_manual_release(tmp_path):
    store = SqliteConversationStore(tmp_path / "stale.db")
    store.initialize()
    now = datetime.now(UTC)
    old = store.claim_generation(_message(), now=now - timedelta(seconds=31))
    current = store.claim_generation(_message(), now=now)
    assert store.complete_generation(
        inbound_message_id=current.inbound_message_id,
        owner_token=current.owner_token,
        reply_body="Vou pedir ajuda à equipe pra seguir com segurança.",
        delivery_state=DeliveryState.PENDING,
        handoff_reason="explicit_human_request",
        now=now,
    )
    handoff = store.list_active_handoffs()[0]
    gate = Barrier(2)

    def stale_complete():
        gate.wait(timeout=3)
        return store.complete_generation(
            inbound_message_id=old.inbound_message_id,
            owner_token=old.owner_token,
            reply_body="unsafe late reply",
            handoff_reason="explicit_human_request",
        )

    def release():
        gate.wait(timeout=3)
        return store.release_handoff(
            conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        stale = pool.submit(stale_complete)
        released = pool.submit(release)
        assert released.result(timeout=4)
        assert not stale.result(timeout=4)
    assert not store.list_active_handoffs()
    assert (
        store.get_generation(provider="test-provider", provider_message_id="inbound-1").reply_body
        == "Vou pedir ajuda à equipe pra seguir com segurança."
    )


def test_other_conversations_keep_processing_during_handoff(tmp_path):
    store = SqliteConversationStore(tmp_path / "isolation.db")
    store.initialize()
    _activate(store)
    assert store.claim_generation(
        _message("another", body="Oi", customer="another-customer")
    ).acquired
    assert store.admit_generation(_message("blocked")).state is GenerationState.SUPPRESSED


def test_retention_purge_does_not_silently_release_active_handoff(tmp_path):
    store = SqliteConversationStore(tmp_path / "purge.db")
    store.initialize()
    old = datetime.now(UTC) - timedelta(days=100)
    claim, handoff = _activate(store, now=old)
    delivery = store.claim_next_delivery(now=old)
    assert store.finalize_delivery(
        delivery_id=delivery.delivery_id,
        owner_token=delivery.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="accepted",
        now=old,
    )
    store.purge_messages_older_than(datetime.now(UTC) - timedelta(days=90))
    assert store.list_active_handoffs() == [handoff]
    assert store.admit_generation(_message("future")).state is GenerationState.SUPPRESSED


def test_local_list_and_explicit_release_omit_customer_data(tmp_path, monkeypatch, capsys):
    path = tmp_path / "cli.db"
    store = SqliteConversationStore(path)
    store.initialize()
    _, handoff = _activate(store)
    monkeypatch.setattr(
        maintenance, "Settings", lambda: Settings(_env_file=None, database_path=path)
    )
    assert maintenance.main(["list-handoffs"]) == 0
    listing = capsys.readouterr().out
    assert f"conversation_id={handoff.conversation_id}" in listing
    assert "explicit_human_request" in listing and handoff.owner_token in listing
    assert "customer" not in listing and "equipe" not in listing
    assert (
        maintenance.main(
            [
                "release-handoff",
                "--conversation-id",
                str(handoff.conversation_id),
                "--owner-token",
                "wrong",
            ]
        )
        == 1
    )
    assert store.list_active_handoffs()
    assert (
        maintenance.main(
            [
                "release-handoff",
                "--conversation-id",
                str(handoff.conversation_id),
                "--owner-token",
                handoff.owner_token,
            ]
        )
        == 0
    )
    assert not store.list_active_handoffs()


def test_terminal_generation_failure_atomically_hands_off_instead_of_continuing(tmp_path):
    class Unavailable(Model):
        def generate(self, *args, **kwargs):
            raise GenerationFailure("provider_unavailable")

    store = SqliteConversationStore(tmp_path / "unavailable.db")
    store.initialize()
    store.admit_generation(_message(body="Oi"))
    result = _processing(store, Unavailable()).run_once()
    assert result is not None and "equipe" in result.reply_body
    assert store.list_active_handoffs()[0].reason_code == "generation_unavailable"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (OutboundRetryableError("not_accepted"), DeliveryState.CANCELLED),
        (OutboundOutcomeUnknown("ambiguous"), DeliveryState.UNKNOWN),
        (OutboundPermanentError("rejected"), DeliveryState.FAILED),
    ],
)
def test_late_result_after_release_preserves_ambiguity_but_cancels_proven_unsent(
    tmp_path, error, expected
):
    store = SqliteConversationStore(tmp_path / "late-result.db")
    store.initialize()
    _, handoff = _activate(store)

    class Sender:
        def send(self, message, *, timeout_seconds):
            assert store.release_handoff(
                conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
            )
            raise error

    result = OutboundDeliveryRunner(store=store, sender=Sender(), timeout_seconds=5).run_once()
    assert result.state is expected
    assert store.claim_next_delivery() is None


def test_release_failure_does_not_expose_automatic_conversation_with_pending_confirmation(tmp_path):
    path = tmp_path / "release-fault.db"
    store = SqliteConversationStore(path)
    store.initialize()
    claim, handoff = _activate(store)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_cancel BEFORE UPDATE OF state ON outbound_deliveries "
            "WHEN NEW.state = 'cancelled' BEGIN SELECT RAISE(ABORT, 'synthetic fault'); END"
        )
    with pytest.raises(PersistenceUnavailable):
        store.release_handoff(
            conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
        )
    assert store.list_active_handoffs() == [handoff]
    assert store.get_delivery_for_inbound(claim.inbound_message_id).state is DeliveryState.PENDING
    assert store.admit_generation(_message("later")).state is GenerationState.SUPPRESSED


def test_sent_confirmation_survives_manual_release_without_resubmission(tmp_path):
    store = SqliteConversationStore(tmp_path / "sent.db")
    store.initialize()
    claim, handoff = _activate(store)
    sender = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("sent-message")])
    runner = OutboundDeliveryRunner(store=store, sender=sender, timeout_seconds=5)
    runner.run_once()
    store.record_delivery_status(
        DeliveryStatusReceived("test-provider", "sent-message", DeliveryStatus.SENT)
    )
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
    )
    assert store.get_delivery_for_inbound(claim.inbound_message_id).state is DeliveryState.SENT
    assert runner.run_once() is None and len(sender.calls) == 1


class PausedProcessingExecutor:
    def __init__(self):
        self.alive = False

    def start(self):
        self.alive = True

    def stop(self):
        self.alive = False

    def wake(self):
        pass

    def is_alive(self):
        return self.alive


def test_meta_early_ack_suppression_survives_lost_ack_release_and_retry(tmp_path):
    path = tmp_path / "meta.db"
    model = Model()
    store = SqliteConversationStore(path)
    app = create_app(
        Settings(
            _env_file=None,
            database_path=path,
            delivery_mode="proactive",
            whatsapp_provider="meta",
            meta_whatsapp_app_secret="synthetic-app-secret",
            meta_whatsapp_verify_token="synthetic-verify-token",
        ),
        store=store,
        generator=model,
        processing_executor=PausedProcessingExecutor(),
        outbound_sender=DeterministicFakeOutboundSender(
            outcomes=[ProviderAcceptance("wamid.confirmation")]
        ),
    )

    def post(client, identifier, text):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "123456789012345"},
                                "messages": [
                                    {
                                        "id": identifier,
                                        "from": "5511000000000",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(b"synthetic-app-secret", body, hashlib.sha256).hexdigest()
        return client.post(
            "/webhooks/meta",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
            },
        )

    with TestClient(app) as client:
        response = post(client, "wamid.first", "Quero falar com uma pessoa")
        assert response.status_code == 200 and "equipe" not in response.text
        assert model.calls == 0
        assert _processing(store, model).run_once() is not None
        handoff = store.list_active_handoffs()[0]
        blocked = post(client, "wamid.suppressed", "Continue")
        assert blocked.status_code == 200
        assert store.release_handoff(
            conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
        )
        retry = post(client, "wamid.suppressed", "Changed body")
        assert retry.status_code == 200 and "equipe" not in retry.text
        assert _processing(store, model).run_once() is None and model.calls == 1
    state = SqliteConversationStore(path).get_generation(
        provider="meta", provider_message_id="wamid.suppressed"
    )
    assert state.state is GenerationState.SUPPRESSED and state.inbound_body == "Continue"


@pytest.mark.parametrize("index", ["ix_handoffs_active", "uq_delivery_handoff_confirmation"])
def test_readiness_rejects_missing_handoff_safety_index(tmp_path, index):
    path = tmp_path / "readiness.db"
    store = SqliteConversationStore(path)
    store.initialize()
    assert store.migrations_are_current()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP INDEX {index}")
    assert not store.migrations_are_current()


def test_database_rejects_generation_and_reply_during_active_handoff(tmp_path):
    path = tmp_path / "database-guards.db"
    store = SqliteConversationStore(path)
    store.initialize()
    _, handoff = _activate(store)
    suppressed = store.admit_generation(_message("later"))
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE message_processing SET state = 'processing', owner_token = 'owner', "
                "lease_expires_at = '2099-01-01T00:00:00+00:00', attempt_count = 1 "
                "WHERE inbound_message_id = ?",
                (suppressed.inbound_message_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO messages (conversation_id, provider, direction, body, created_at, "
                "in_reply_to_message_id) VALUES (?, 'test-provider', 'outbound', 'unsafe', ?, ?)",
                (
                    handoff.conversation_id,
                    handoff.activated_at.isoformat(),
                    suppressed.inbound_message_id,
                ),
            )
    assert (
        store.get_generation(provider="test-provider", provider_message_id="later").state
        is GenerationState.SUPPRESSED
    )


def test_technical_symptom_keeps_safety_guidance_even_when_generation_fails(tmp_path):
    store = SqliteConversationStore(tmp_path / "symptom-failure.db")
    store.initialize()

    class FailingModel(Model):
        def generate(self, *args, **kwargs):
            raise GenerationFailure("invalid_structured_decision")

    store.admit_generation(_message(body="Meu couro cabeludo está ardendo"))
    result = _processing(store, FailingModel()).run_once()
    assert "pare" in result.reply_body
    assert "avaliação profissional" in result.reply_body
    assert "atendimento médico urgente" in result.reply_body
    assert store.list_active_handoffs()[0].reason_code == "personalized_technical_risk"


def test_activation_cancels_only_proven_unsubmitted_legacy_work(tmp_path):
    store = SqliteConversationStore(tmp_path / "pending-at-activation.db")
    store.initialize()
    claim = store.claim_generation(_message())
    # The public legacy persistence seam can hold old prepared replies during
    # cutover. An unrendered reply differs from one authorized for HTTP rendering.
    store.get_or_create_reply(_message("unrendered"), "old prepared reply")
    unsent = store.get_delivery_for_provider_inbound(
        provider="test-provider", provider_message_id="unrendered"
    )
    store.get_or_create_reply(_message("possibly-rendered"), "old authorized reply")
    ambiguous = store.get_delivery_for_provider_inbound(
        provider="test-provider", provider_message_id="possibly-rendered"
    )
    assert store.authorize_legacy_reply(delivery_id=ambiguous.delivery_id)
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Vou pedir ajuda à equipe pra seguir com segurança.",
        delivery_state=DeliveryState.PENDING,
        handoff_reason="explicit_human_request",
    )
    assert store.get_delivery(unsent.delivery_id).state is DeliveryState.CANCELLED
    assert store.get_delivery(ambiguous.delivery_id).state is DeliveryState.UNKNOWN
    assert store.get_delivery_for_inbound(claim.inbound_message_id).state is DeliveryState.PENDING
    assert not store.authorize_legacy_reply(delivery_id=unsent.delivery_id)
    assert not store.authorize_legacy_reply(delivery_id=ambiguous.delivery_id)


def test_database_allows_only_one_confirmation_delivery_per_handoff_episode(tmp_path):
    path = tmp_path / "confirmation-unique.db"
    store = SqliteConversationStore(path)
    store.initialize()
    _, handoff = _activate(store)
    other = store.claim_generation(_message("other", body="Oi", customer="other-customer"))
    assert store.complete_generation(
        inbound_message_id=other.inbound_message_id,
        owner_token=other.owner_token,
        reply_body="Como posso te ajudar?",
        delivery_state=DeliveryState.PENDING,
    )
    delivery = store.get_delivery_for_inbound(other.inbound_message_id)
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE outbound_deliveries SET handoff_token = ? WHERE id = ?",
            (handoff.owner_token, delivery.delivery_id),
        )
    assert store.get_delivery(delivery.delivery_id).handoff_token is None
