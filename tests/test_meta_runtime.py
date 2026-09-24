import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from rj_studio_ai.config import Settings
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import InboundMessageReceived, OutboundMessage
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import OutboundOutcomeUnknown, ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.providers.meta import MetaOutboundMessageSender

APP_SECRET = "meta-app-secret"
VERIFY_TOKEN = "meta-verify-token"
PHONE_NUMBER_ID = "123456789012345"
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


class _PausedExecutor:
    def __init__(self) -> None:
        self.alive = False
        self.wakes = 0

    def start(self) -> None:
        self.alive = True

    def stop(self) -> None:
        self.alive = False

    def wake(self) -> None:
        self.wakes += 1

    def is_alive(self) -> bool:
        return self.alive


def _settings(database_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        whatsapp_provider="meta",
        delivery_mode="proactive",
        meta_whatsapp_verify_token=VERIFY_TOKEN,
        meta_whatsapp_app_secret=APP_SECRET,
        meta_whatsapp_access_token="meta-access-token",
        meta_whatsapp_phone_number_id=PHONE_NUMBER_ID,
        meta_whatsapp_api_version="v24.0",
        **overrides,
    )


def _payload(*, message_id: str = "wamid.inbound-runtime") -> dict[str, object]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-synthetic",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                            "messages": [
                                {
                                    "from": "5511999999999",
                                    "id": message_id,
                                    "timestamp": "1790000000",
                                    "type": "text",
                                    "text": {"body": "Mensagem sintética"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _signed_body(payload: dict[str, object]) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": f"sha256={digest}",
    }


def test_meta_verification_accepts_only_matching_token(tmp_path: Path) -> None:
    app = create_app(
        _settings(tmp_path / "verification.db"),
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
        processing_executor=_PausedExecutor(),
    )

    with TestClient(app) as client:
        valid = client.get(
            "/webhooks/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "challenge-synthetic",
            },
        )
        invalid = client.get(
            "/webhooks/meta",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "challenge-synthetic",
            },
        )

    assert valid.status_code == 200
    assert valid.text == "challenge-synthetic"
    assert invalid.status_code == 403


def test_meta_inbound_is_durable_before_ack_and_replay_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "meta-ingress.db"
    executor = _PausedExecutor()
    app = create_app(
        _settings(database_path),
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
        processing_executor=executor,
    )
    body, headers = _signed_body(_payload())

    with TestClient(app) as client:
        first = client.post("/webhooks/meta", content=body, headers=headers)
        duplicate = client.post("/webhooks/meta", content=body, headers=headers)

    assert first.status_code == duplicate.status_code == 200
    assert first.text == duplicate.text == ""
    store = SqliteConversationStore(database_path)
    assert len(store.get_history(provider="meta", customer_address="5511999999999")) == 1
    assert executor.wakes == 2


def test_authenticated_meta_batch_rolls_back_all_events_on_second_insert_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "batch-rollback.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_second_meta_message
            BEFORE INSERT ON messages
            WHEN NEW.body = 'Second'
            BEGIN SELECT RAISE(ABORT, 'synthetic second insert failure'); END
            """
        )
    events = (
        InboundMessageReceived("meta", "wamid.first", "customer", PHONE_NUMBER_ID, "First"),
        InboundMessageReceived("meta", "wamid.second", "customer", PHONE_NUMBER_ID, "Second"),
    )

    try:
        store.record_webhook_events(events)
    except PersistenceUnavailable:
        pass
    else:
        raise AssertionError("Synthetic batch failure did not roll back")

    assert store.get_history(provider="meta", customer_address="customer") == []


def test_meta_free_form_policy_uses_recent_durable_customer_message(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "window.db")
    store.initialize()
    recent = InboundMessageReceived("meta", "wamid.recent", "5511999999999", PHONE_NUMBER_ID, "Olá")
    store.admit_generation(recent, now=NOW)

    assert store.meta_free_form_is_eligible(
        OutboundMessage(PHONE_NUMBER_ID, "5511999999999", "Resposta"),
        now=NOW + timedelta(hours=23, minutes=59),
    )
    assert not store.meta_free_form_is_eligible(
        OutboundMessage(PHONE_NUMBER_ID, "5511999999999", "Resposta"),
        now=NOW + timedelta(hours=24, seconds=1),
    )
    assert not store.meta_free_form_is_eligible(
        OutboundMessage(PHONE_NUMBER_ID, "5511888888888", "Resposta"),
        now=NOW + timedelta(hours=1),
    )


def test_meta_durable_outbox_acceptance_and_unknown_follow_existing_lifecycle(
    tmp_path: Path,
) -> None:
    store = SqliteConversationStore(tmp_path / "outbox.db")
    store.initialize()
    for suffix in ("accepted", "unknown"):
        claim = store.claim_generation(
            InboundMessageReceived(
                "meta",
                f"wamid.inbound-{suffix}",
                f"customer-{suffix}",
                PHONE_NUMBER_ID,
                "Olá",
            ),
            now=NOW,
        )
        assert claim.owner_token is not None
        assert store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Resposta",
            delivery_state=DeliveryState.PENDING,
            now=NOW + timedelta(seconds=1),
        )

    accepted_runner = OutboundDeliveryRunner(
        store=store,
        sender=DeterministicFakeOutboundSender(
            outcomes=[ProviderAcceptance("wamid.outbound-accepted")]
        ),
        timeout_seconds=2,
    )
    accepted = accepted_runner.run_once(now=NOW + timedelta(seconds=2))
    assert accepted is not None and accepted.state is DeliveryState.ACCEPTED

    unknown_sender = DeterministicFakeOutboundSender(outcomes=[OutboundOutcomeUnknown("ambiguous")])
    unknown_runner = OutboundDeliveryRunner(
        store=store,
        sender=unknown_sender,
        timeout_seconds=2,
    )
    unknown = unknown_runner.run_once(now=NOW + timedelta(seconds=3))
    assert unknown is not None and unknown.state is DeliveryState.UNKNOWN
    assert unknown_runner.run_once(now=NOW + timedelta(minutes=5)) is None
    assert len(unknown_sender.calls) == 1


def test_meta_runner_never_claims_pending_twilio_delivery(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "provider-routing.db")
    store.initialize()
    inbound_ids: dict[str, int] = {}
    for provider in ("twilio", "meta"):
        claim = store.claim_generation(
            InboundMessageReceived(
                provider,
                f"provider-inbound-{provider}",
                f"customer-{provider}",
                PHONE_NUMBER_ID,
                "Olá",
            ),
            now=NOW,
        )
        assert claim.owner_token is not None
        assert store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Resposta",
            delivery_state=DeliveryState.PENDING,
            now=NOW + timedelta(seconds=1),
        )
        inbound_ids[provider] = claim.inbound_message_id
    sender = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("wamid.meta-outbound")])

    result = OutboundDeliveryRunner(
        store=store,
        sender=sender,
        timeout_seconds=2,
        provider="meta",
    ).run_once(now=NOW + timedelta(seconds=2))

    assert result is not None
    assert result.inbound_message_id == inbound_ids["meta"]
    twilio_delivery = store.get_delivery_for_inbound(inbound_ids["twilio"])
    assert twilio_delivery is not None
    assert twilio_delivery.state is DeliveryState.PENDING


def test_meta_sender_readiness_is_local_and_does_not_call_graph(tmp_path: Path) -> None:
    calls: list[object] = []
    sender = MetaOutboundMessageSender(
        access_token="meta-access-token",
        phone_number_id=PHONE_NUMBER_ID,
        api_version="v24.0",
        free_form_is_eligible=lambda _: True,
        post=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    app = create_app(
        _settings(tmp_path / "ready.db"),
        outbound_sender=sender,
        processing_executor=_PausedExecutor(),
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert calls == []
