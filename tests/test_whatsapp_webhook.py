import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from rj_studio_ai.config import Settings
from rj_studio_ai.domain import (
    AIReply,
    InboundMessage,
    InboundMessageReceived,
    OutboundMessage,
    ProviderWebhookEventBatch,
)
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import (
    ProviderAcceptance,
    ProviderWebhookRequest,
    ProviderWebhookResponse,
    WhatsAppProvider,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

TWILIO_FORM = {
    "MessageSid": "SM-first-message",
    "From": "whatsapp:+5511999999999",
    "To": "whatsapp:+14155238886",
    "Body": "Olá, quero marcar um horário",
}


class FailFirstReplyProvider(WhatsAppProvider):
    def __init__(self) -> None:
        self.reply_attempts = 0
        self.received_request: ProviderWebhookRequest | None = None

    def receive(self, webhook: ProviderWebhookRequest) -> ProviderWebhookEventBatch:
        self.received_request = webhook
        return ProviderWebhookEventBatch(
            events=(
                InboundMessageReceived(
                    provider="test-provider",
                    provider_message_id="provider-message-1",
                    customer_address="customer-1",
                    recipient_address="studio",
                    body="Mensagem sintética",
                ),
            )
        )

    def acknowledge(self) -> ProviderWebhookResponse:
        return ProviderWebhookResponse(body="", media_type="text/plain")

    def render_legacy_reply(self, reply: AIReply) -> ProviderWebhookResponse:
        self.reply_attempts += 1
        if self.reply_attempts == 1:
            raise RuntimeError("synthetic rendering failure")
        return ProviderWebhookResponse(body=reply.body, media_type="text/plain")

    def is_configured(self) -> bool:
        return True


class SignallingFakeOutboundSender(DeterministicFakeOutboundSender):
    def __init__(self, *, outcomes: list[ProviderAcceptance]) -> None:
        super().__init__(outcomes=outcomes)
        self.called = Event()

    def send(
        self,
        message: OutboundMessage,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        result = super().send(message, timeout_seconds=timeout_seconds)
        self.called.set()
        return result


def test_customer_message_is_replied_to_and_persisted(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    settings = Settings(
        _env_file=None,
        database_path=database_path,
        automatic_reply="Oi! Recebemos sua mensagem.",
        twilio_validate_signature=False,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/whatsapp",
            data=TWILIO_FORM,
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "Oi! Recebemos sua mensagem." in response.text

    history = SqliteConversationStore(database_path).get_history(
        provider="twilio",
        customer_address="whatsapp:+5511999999999",
    )
    assert [(message.direction, message.body) for message in history] == [
        ("inbound", "Olá, quero marcar um horário"),
        ("outbound", "Oi! Recebemos sua mensagem."),
    ]
    store = SqliteConversationStore(database_path)
    generation = store.get_generation(
        provider="twilio",
        provider_message_id=TWILIO_FORM["MessageSid"],
    )
    assert generation is not None
    delivery = store.get_delivery_for_inbound(generation.inbound_message_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.ACCEPTED_LEGACY


def test_twilio_named_route_accepts_the_same_v0_callback(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert response.status_code == 200
    assert "<Message>" in response.text


def test_current_webhook_keeps_twiml_and_does_not_call_outbound_sender(tmp_path: Path) -> None:
    sender = DeterministicFakeOutboundSender(
        outcomes=[ProviderAcceptance(provider_message_id="must-not-be-used")]
    )
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            automatic_reply="Resposta síncrona",
            twilio_validate_signature=False,
        ),
        outbound_sender=sender,
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert response.status_code == 200
    assert "<Message>Resposta síncrona</Message>" in response.text
    assert sender.calls == []


def test_proactive_mode_acknowledges_without_twiml_and_sends_one_rest_message(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "proactive.db"
    sender = SignallingFakeOutboundSender(
        outcomes=[ProviderAcceptance(provider_message_id="PM-proactive")]
    )
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta proativa",
            twilio_validate_signature=False,
            delivery_mode="proactive",
            outbound_poll_interval_seconds=0.05,
        ),
        outbound_sender=sender,
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=TWILIO_FORM)
        assert sender.called.wait(timeout=2.0)
        replay = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert response.status_code == replay.status_code == 200
    assert "<Message>" not in response.text
    assert "Resposta proativa" not in response.text
    assert "<Message>" not in replay.text
    assert len(sender.calls) == 1
    assert sender.calls[0][0].sender_address == TWILIO_FORM["To"]
    assert sender.calls[0][0].recipient_address == TWILIO_FORM["From"]
    assert sender.calls[0][0].body == "Resposta proativa"
    store = SqliteConversationStore(database_path)
    generation = store.get_generation(
        provider="twilio",
        provider_message_id=TWILIO_FORM["MessageSid"],
    )
    assert generation is not None
    delivery = store.get_delivery_for_inbound(generation.inbound_message_id)
    assert delivery is not None
    assert delivery.state is DeliveryState.ACCEPTED
    assert delivery.provider_message_id == "PM-proactive"


def test_legacy_rollback_cannot_render_a_reply_already_sent_proactively(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mode-cutover.db"
    sender = SignallingFakeOutboundSender(
        outcomes=[ProviderAcceptance(provider_message_id="PM-cutover")]
    )
    proactive_app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Uma única resposta",
            twilio_validate_signature=False,
            delivery_mode="proactive",
            outbound_poll_interval_seconds=0.05,
        ),
        outbound_sender=sender,
    )
    with TestClient(proactive_app) as client:
        proactive = client.post("/webhooks/twilio", data=TWILIO_FORM)
        assert sender.called.wait(timeout=2.0)

    legacy_app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Uma única resposta",
            twilio_validate_signature=False,
            delivery_mode="legacy",
        )
    )
    with TestClient(legacy_app) as client:
        legacy_retry = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert proactive.status_code == 200
    assert "<Message>" not in proactive.text
    assert legacy_retry.status_code == 200
    assert "Uma única resposta" not in legacy_retry.text
    assert len(sender.calls) == 1


def test_retried_twilio_message_replays_persisted_reply_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "conversations.db"
    first_app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta original",
            twilio_validate_signature=False,
        )
    )

    with TestClient(first_app) as client:
        first_response = client.post("/webhooks/whatsapp", data=TWILIO_FORM)

    restarted_app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta alterada",
            twilio_validate_signature=False,
        )
    )
    with TestClient(restarted_app) as client:
        retry_response = client.post("/webhooks/whatsapp", data=TWILIO_FORM)

    assert first_response.status_code == 200
    assert retry_response.status_code == 200
    assert "Resposta original" in first_response.text
    assert "Resposta original" in retry_response.text
    assert "Resposta alterada" not in retry_response.text
    history = SqliteConversationStore(database_path).get_history(
        provider="twilio",
        customer_address=TWILIO_FORM["From"],
    )
    assert len(history) == 2


def test_concurrent_retries_share_one_persisted_reply(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta concorrente",
            twilio_validate_signature=False,
        )
    )
    attempts = 8
    barrier = Barrier(attempts)

    with TestClient(app) as client:

        def send_callback() -> tuple[int, str]:
            barrier.wait()
            response = client.post("/webhooks/whatsapp", data=TWILIO_FORM)
            return response.status_code, response.text

        with ThreadPoolExecutor(max_workers=attempts) as executor:
            responses = list(executor.map(lambda _: send_callback(), range(attempts)))

    assert all(status_code == 200 for status_code, _ in responses)
    assert all("Resposta concorrente" in body for _, body in responses)
    history = SqliteConversationStore(database_path).get_history(
        provider="twilio",
        customer_address=TWILIO_FORM["From"],
    )
    assert [(message.direction, message.body) for message in history] == [
        ("inbound", TWILIO_FORM["Body"]),
        ("outbound", "Resposta concorrente"),
    ]


def test_retry_does_not_advance_conversation_activity(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        client.post("/webhooks/whatsapp", data=TWILIO_FORM)
        with sqlite3.connect(database_path) as connection:
            initial_timestamp = connection.execute(
                "SELECT updated_at FROM conversations"
            ).fetchone()[0]
        client.post("/webhooks/whatsapp", data=TWILIO_FORM)

    with sqlite3.connect(database_path) as connection:
        retry_timestamp = connection.execute("SELECT updated_at FROM conversations").fetchone()[0]

    assert retry_timestamp == initial_timestamp


def test_reply_render_failure_is_recovered_by_retry(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    provider = FailFirstReplyProvider()
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta durável",
            twilio_validate_signature=False,
        ),
        provider=provider,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        first_response = client.post(
            "/webhooks/twilio",
            content=b"provider-specific-payload",
            headers={"Content-Type": "application/octet-stream"},
        )
        store = SqliteConversationStore(database_path)
        generation = store.get_generation(
            provider="test-provider",
            provider_message_id="provider-message-1",
        )
        assert generation is not None
        delivery_after_failure = store.get_delivery_for_inbound(generation.inbound_message_id)
        assert delivery_after_failure is not None
        assert delivery_after_failure.state is DeliveryState.UNKNOWN
        assert delivery_after_failure.safe_error_code == "legacy_unverified"

        retry_response = client.post(
            "/webhooks/twilio",
            content=b"provider-specific-payload",
            headers={"Content-Type": "application/octet-stream"},
        )

    assert first_response.status_code == 500
    assert retry_response.status_code == 200
    assert retry_response.text == "Resposta durável"
    assert provider.received_request is not None
    assert provider.received_request.body == b"provider-specific-payload"
    delivery_after_retry = SqliteConversationStore(database_path).get_delivery_for_inbound(
        generation.inbound_message_id
    )
    assert delivery_after_retry is not None
    assert delivery_after_retry.state is DeliveryState.ACCEPTED_LEGACY
    history = SqliteConversationStore(database_path).get_history(
        provider="test-provider",
        customer_address="customer-1",
    )
    assert len(history) == 2


def test_database_failure_returns_retryable_error_without_twiml(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        database_path.write_bytes(b"corrupted database")
        response = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert response.status_code == 503
    assert "<Message>" not in response.text


def test_invalid_twilio_signature_is_rejected_without_persistence(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_auth_token="sandbox-secret",
            twilio_validate_signature=True,
            twilio_public_webhook_url="https://example.ngrok.app/webhooks/whatsapp",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/whatsapp",
            data=TWILIO_FORM,
            headers={"X-Twilio-Signature": "invalid"},
        )

    assert response.status_code == 403
    history = SqliteConversationStore(database_path).get_history(
        provider="twilio",
        customer_address=TWILIO_FORM["From"],
    )
    assert history == []


def test_missing_twilio_configuration_is_an_availability_failure(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            twilio_auth_token="",
            twilio_public_webhook_url=None,
            twilio_validate_signature=True,
        )
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert response.status_code == 503


def test_incomplete_twilio_payload_is_rejected_without_persistence(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )
    incomplete_form = {key: value for key, value in TWILIO_FORM.items() if key != "Body"}

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=incomplete_form)

    assert response.status_code == 400
    history = SqliteConversationStore(database_path).get_history(
        provider="twilio",
        customer_address=TWILIO_FORM["From"],
    )
    assert history == []


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"{}", "application/json"),
        (b"Body=%FF", "application/x-www-form-urlencoded"),
    ],
)
def test_malformed_twilio_payload_is_rejected(
    tmp_path: Path,
    body: bytes,
    content_type: str,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            content=body,
            headers={"Content-Type": content_type},
        )

    assert response.status_code == 400


def test_valid_twilio_signature_is_accepted(tmp_path: Path) -> None:
    auth_token = "sandbox-secret"
    public_url = "https://example.ngrok.app/webhooks/whatsapp"
    form_with_new_field = {**TWILIO_FORM, "FutureTwilioField": "included"}
    signature = RequestValidator(auth_token).compute_signature(
        public_url,
        form_with_new_field,
    )
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            twilio_auth_token=auth_token,
            twilio_validate_signature=True,
            twilio_public_webhook_url=public_url,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/whatsapp",
            data=form_with_new_field,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 200


def test_health_endpoint_reports_process_liveness(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint_reports_usable_local_instance(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            automatic_reply="Resposta configurada",
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "configuration": "ok",
            "sqlite_single_process": "ok",
            "database": "ok",
            "migrations": "ok",
            "sqlite_storage": "ok",
            "sqlite_journal_mode": "ok",
            "sqlite_synchronous": "ok",
            "sqlite_foreign_keys": "ok",
            "sqlite_busy_timeout": "ok",
            "delivery_mode": "ok",
        },
    }


def test_proactive_readiness_requires_live_outbound_executor(tmp_path: Path) -> None:
    sender = SignallingFakeOutboundSender(outcomes=[])
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "proactive-readiness.db",
            twilio_validate_signature=False,
            delivery_mode="proactive",
        ),
        outbound_sender=sender,
    )

    with TestClient(app) as client:
        ready = client.get("/ready")
        app.state.outbound_executor.stop()
        stopped = client.get("/ready")

    assert ready.status_code == 200
    assert ready.json()["checks"]["outbound_executor"] == "ok"
    assert stopped.status_code == 503
    assert stopped.json()["checks"]["outbound_executor"] == "failed"


def test_proactive_readiness_rejects_missing_twilio_rest_configuration(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "missing-outbound-config.db",
            twilio_validate_signature=False,
            delivery_mode="proactive",
        )
    )

    with TestClient(app) as client:
        ready = client.get("/ready")
        webhook = client.post("/webhooks/twilio", data=TWILIO_FORM)

    assert ready.status_code == 503
    assert ready.json()["checks"]["configuration"] == "failed"
    assert ready.json()["checks"]["outbound_executor"] == "failed"
    assert webhook.status_code == 503


def test_legacy_readiness_rejects_unresolved_proactive_delivery(tmp_path: Path) -> None:
    database_path = tmp_path / "unsafe-rollback.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    claim = store.claim_generation(
        InboundMessage(
            provider="twilio",
            provider_message_id="SM-unsafe-rollback",
            customer_address="customer",
            recipient_address="studio",
            body="Mensagem sintética",
        )
    )
    assert claim.owner_token is not None
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Resposta pendente",
        delivery_state=DeliveryState.PENDING,
    )
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
            delivery_mode="legacy",
        ),
        store=store,
    )

    with TestClient(app) as client:
        ready = client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["checks"]["delivery_mode"] == "failed"


def test_ready_endpoint_rejects_missing_provider_configuration(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "conversations.db",
            twilio_auth_token="",
            twilio_public_webhook_url=None,
            twilio_validate_signature=True,
        )
    )

    with TestClient(app) as client:
        health_response = client.get("/health")
        ready_response = client.get("/ready")

    assert health_response.status_code == 200
    assert ready_response.status_code == 503
    assert ready_response.json()["checks"] == {
        "configuration": "failed",
        "sqlite_single_process": "ok",
        "database": "ok",
        "migrations": "ok",
        "sqlite_storage": "ok",
        "sqlite_journal_mode": "ok",
        "sqlite_synchronous": "ok",
        "sqlite_foreign_keys": "ok",
        "sqlite_busy_timeout": "ok",
        "delivery_mode": "ok",
    }


def test_ready_endpoint_rejects_stale_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        with sqlite3.connect(database_path) as connection:
            connection.execute("UPDATE alembic_version SET version_num = '0001_v0_schema'")
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["migrations"] == "failed"


def test_ready_endpoint_rejects_missing_required_table(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        with sqlite3.connect(database_path) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DROP TABLE conversations")
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["migrations"] == "failed"


def test_ready_endpoint_rejects_inaccessible_database(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        database_path.write_bytes(b"corrupted database")
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "failed"
    assert response.json()["checks"]["migrations"] == "failed"
