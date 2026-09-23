from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from rj_studio_ai.config import Settings
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
MESSAGE_SID = "SM" + "1" * 32


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        twilio_validate_signature=False,
    )


def _pending(store: SqliteConversationStore) -> int:
    claim = store.claim_generation(
        InboundMessage(
            provider="twilio",
            provider_message_id="SM-status-inbound",
            customer_address="whatsapp:+5511999999999",
            recipient_address="whatsapp:+14155238886",
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


def test_twilio_status_callback_buffers_early_evidence_and_tolerates_extra_fields(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "callback.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    inbound_id = _pending(store)
    app = create_app(_settings(database_path), store=store)

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio/status",
            data={
                "MessageSid": MESSAGE_SID,
                "MessageStatus": "delivered",
                "FutureTwilioParameter": "ignored",
            },
        )

    assert response.status_code == 200
    assert "<Message>" not in response.text
    finalized = OutboundDeliveryRunner(
        store=SqliteConversationStore(database_path),
        sender=DeterministicFakeOutboundSender(
            outcomes=[ProviderAcceptance(provider_message_id=MESSAGE_SID)]
        ),
        timeout_seconds=2.0,
    ).run_once(now=NOW + timedelta(seconds=2))
    assert finalized is not None
    assert finalized.state is DeliveryState.DELIVERED
    assert (
        SqliteConversationStore(database_path).get_delivery_for_inbound(inbound_id).state
        is DeliveryState.DELIVERED
    )


def test_twilio_status_callback_rejects_invalid_payload(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path / "invalid-callback.db"))

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio/status",
            data={"MessageStatus": "delivered"},
        )

    assert response.status_code == 400


def test_twilio_status_callback_route_validates_signature(tmp_path: Path) -> None:
    auth_token = "callback-auth-token"
    public_url = "https://public.example/webhooks/twilio/status"
    form = {
        "MessageSid": MESSAGE_SID,
        "MessageStatus": "sent",
        "AdditionalField": "included",
    }
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "signed-callback.db",
            twilio_auth_token=auth_token,
            twilio_validate_signature=True,
            twilio_public_webhook_url="https://public.example/webhooks/twilio",
            twilio_status_callback_url=public_url,
        )
    )
    signature = RequestValidator(auth_token).compute_signature(public_url, form)

    with TestClient(app) as client:
        valid = client.post(
            "/webhooks/twilio/status",
            data=form,
            headers={"X-Twilio-Signature": signature},
        )
        invalid = client.post(
            "/webhooks/twilio/status",
            data=form,
            headers={"X-Twilio-Signature": "invalid"},
        )

    assert valid.status_code == 200
    assert invalid.status_code == 403
