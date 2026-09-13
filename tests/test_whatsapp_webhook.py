from pathlib import Path

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import SqliteConversationStore

TWILIO_FORM = {
    "MessageSid": "SM-first-message",
    "From": "whatsapp:+5511999999999",
    "To": "whatsapp:+14155238886",
    "Body": "Olá, quero marcar um horário",
}


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


def test_retried_twilio_message_is_not_replied_to_or_persisted_twice(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "conversations.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        first_response = client.post("/webhooks/whatsapp", data=TWILIO_FORM)
        retry_response = client.post("/webhooks/whatsapp", data=TWILIO_FORM)

    assert first_response.status_code == 200
    assert retry_response.status_code == 200
    assert "<Message>" in first_response.text
    assert "<Message>" not in retry_response.text
    history = SqliteConversationStore(database_path).get_history(
        provider="twilio",
        customer_address=TWILIO_FORM["From"],
    )
    assert len(history) == 2


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


def test_valid_twilio_signature_is_accepted(tmp_path: Path) -> None:
    auth_token = "sandbox-secret"
    public_url = "https://example.ngrok.app/webhooks/whatsapp"
    signature = RequestValidator(auth_token).compute_signature(public_url, TWILIO_FORM)
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
            data=TWILIO_FORM,
            headers={"X-Twilio-Signature": signature},
        )

    assert response.status_code == 200


def test_health_endpoint_reports_ready(tmp_path: Path) -> None:
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
