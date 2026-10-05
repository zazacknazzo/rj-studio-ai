"""Signed provider ingress through the real runtime, with all networks controlled."""

import hashlib
import hmac
import json
from datetime import date
from time import monotonic, sleep
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from requests import Timeout
from twilio.request_validator import RequestValidator

from rj_studio_ai.config import Settings
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.evaluation.suite import fixture_decision
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.meta import MetaOutboundMessageSender
from rj_studio_ai.providers.openai import OpenAIReplyGenerator
from rj_studio_ai.providers.twilio import TwilioOutboundSender
from rj_studio_ai.salon_knowledge import SalonKnowledgeFact

AUTH = "synthetic-signature-secret"
PHONE_ID = "123456789012345"
INBOUND_URL = "https://synthetic.example/webhooks/twilio"
STATUS_URL = INBOUND_URL + "/status"


@pytest.fixture(autouse=True)
def prohibit_uncontrolled_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Preflight must not use an uncontrolled network transport")

    async def async_forbidden(*args, **kwargs):
        forbidden()

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_forbidden)


def post_signed(client, provider, *, status=None, valid_signature=True):
    if provider == "twilio":
        form = (
            {"MessageSid": "SM" + "b" * 32, "MessageStatus": status, "FutureField": "ignored"}
            if status
            else {
                "MessageSid": "SM" + "a" * 32,
                "From": "whatsapp:+5511000000001",
                "To": "whatsapp:+1415000000001",
                "Body": "Quanto custa o corte?",
            }
        )
        url = STATUS_URL if status else INBOUND_URL
        signature = RequestValidator(AUTH).compute_signature(url, form)
        return client.post(
            "/webhooks/twilio/status" if status else "/webhooks/twilio",
            data=form,
            headers={"X-Twilio-Signature": signature if valid_signature else "invalid"},
        )
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": PHONE_ID},
        "statuses" if status else "messages": [
            {"id": "wamid.synthetic-outbound", "status": status, "future_field": "ignored"}
            if status
            else {
                "id": "wamid.synthetic-inbound",
                "from": "5511000000001",
                "type": "text",
                "text": {"body": "Quanto custa o corte?"},
            }
        ],
    }
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "synthetic-waba", "changes": [{"field": "messages", "value": value}]}],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(AUTH.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/meta",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=" + (signature if valid_signature else "invalid"),
        },
    )


def controlled_pipeline(tmp_path, provider, *, unknown=False):
    knowledge_path = tmp_path / "synthetic.yaml"
    fact = SalonKnowledgeFact(
        id="price-corte",
        topic="corte",
        category="price",
        status="approved",
        fact_type="operational_commercial",
        statement="O corte custa R$ 120,00.",
        source="synthetic preflight fixture",
        reviewed_at=date(2026, 10, 5),
        approved_by="synthetic-operator",
    )
    knowledge_path.write_text(
        json.dumps({"version": 1, "facts": [fact.model_dump(mode="json")]}), encoding="utf-8"
    )
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "preflight.db",
        salon_knowledge_path=knowledge_path,
        llm_provider="openai",
        openai_api_key="synthetic-openai-key",
        whatsapp_provider=provider,
        delivery_mode="proactive",
        twilio_validate_signature=True,
        twilio_auth_token=AUTH,
        twilio_public_webhook_url=INBOUND_URL,
        twilio_status_callback_url=STATUS_URL,
        meta_whatsapp_app_secret=AUTH,
        meta_whatsapp_verify_token="synthetic-verify-token",
        meta_whatsapp_access_token="synthetic-meta-token",
        meta_whatsapp_phone_number_id=PHONE_ID,
        meta_whatsapp_api_version="v24.0",
        processing_poll_interval_seconds=0.01,
        outbound_poll_interval_seconds=0.01,
    )
    store = SqliteConversationStore(settings.database_path)
    model_calls, outbound_calls = [], []
    decision = fixture_decision(
        surface="agentic",
        intents=["price"],
        knowledge_refs=["price-corte"],
        reply_text="O corte custa R$ 1,00.",
        reply_parts=[{"kind": "fact", "knowledge_ref": "price-corte"}],
    )

    def model_response(request):
        model_calls.append(request)
        assert request.url.path == "/v1/responses"
        payload = json.loads(request.content)
        assert payload["reasoning"]["effort"] == "low"
        assert payload["max_output_tokens"] == 1024
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "status": "completed",
                "service_tier": "default",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 5},
                },
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": decision.model_dump_json()}],
                    }
                ],
            },
        )

    generator = OpenAIReplyGenerator(
        api_key="synthetic-openai-key",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(model_response)),
    )

    def twilio_create(**kwargs):
        outbound_calls.append(kwargs)
        assert kwargs["from_"] == "whatsapp:+1415000000001"
        assert kwargs["to"] == "whatsapp:+5511000000001"
        assert kwargs["status_callback"] == STATUS_URL
        if unknown:
            raise Timeout("Synthetic lost response")
        return SimpleNamespace(sid="SM" + "b" * 32, status="queued")

    def meta_post(url, **kwargs):
        outbound_calls.append(kwargs["json"])
        assert url == f"https://graph.facebook.com/v24.0/{PHONE_ID}/messages"
        assert kwargs["json"]["to"] == "5511000000001"
        if unknown:
            raise Timeout("Synthetic lost response")
        return httpx.Response(200, json={"messages": [{"id": "wamid.synthetic-outbound"}]})

    sender = (
        TwilioOutboundSender(
            account_sid="AC" + "a" * 32,
            api_key_sid="SK" + "b" * 32,
            api_key_secret="synthetic-api-secret",
            status_callback_url=STATUS_URL,
            client_factory=lambda _: SimpleNamespace(
                messages=SimpleNamespace(create=twilio_create)
            ),
        )
        if provider == "twilio"
        else MetaOutboundMessageSender(
            access_token="synthetic-meta-token",
            phone_number_id=PHONE_ID,
            api_version="v24.0",
            free_form_is_eligible=store.meta_free_form_is_eligible,
            post=meta_post,
        )
    )
    return settings, store, generator, sender, model_calls, outbound_calls


def await_delivery(store, provider, expected):
    inbound_id = "SM" + "a" * 32 if provider == "twilio" else "wamid.synthetic-inbound"
    expires = monotonic() + 3
    while monotonic() < expires:
        delivery = store.get_delivery_for_provider_inbound(
            provider=provider, provider_message_id=inbound_id
        )
        if delivery and delivery.state == expected:
            return delivery
        sleep(0.005)
    raise AssertionError(f"Controlled {provider} pipeline did not reach {expected}")


@pytest.mark.parametrize("provider", ["twilio", "meta"])
@pytest.mark.parametrize("status", ["sent", "delivered", "read", "failed"])
def test_signed_webhook_openai_trusted_outbox_status_and_restart(tmp_path, provider, status):
    settings, store, generator, sender, model_calls, outbound_calls = controlled_pipeline(
        tmp_path, provider
    )

    def app_for(current_store):
        return create_app(
            settings, store=current_store, generator=generator, outbound_sender=sender
        )

    with TestClient(app_for(store)) as client:
        assert client.get("/ready").status_code == 200
        assert post_signed(client, provider, valid_signature=False).status_code == 403
        customer = "whatsapp:+5511000000001" if provider == "twilio" else "5511000000001"
        assert store.get_history(provider=provider, customer_address=customer) == []
        first = post_signed(client, provider)
        assert first.status_code == 200
        assert "<Message>" not in first.text  # Never TwiML + REST.
        assert post_signed(client, provider).status_code == 200
        accepted = await_delivery(store, provider, DeliveryState.ACCEPTED)
        assert "R$ 120,00" in accepted.body
        assert "R$ 1,00" not in accepted.body
        assert accepted.provider_message_id == (
            "SM" + "b" * 32 if provider == "twilio" else "wamid.synthetic-outbound"
        )
        metric = store.get_generation_metrics(inbound_message_id=accepted.inbound_message_id)[0]
        assert metric.response_status == "completed"
        assert metric.reasoning_tokens == 5
        for _ in range(2):
            assert post_signed(client, provider, status=status).status_code == 200
        terminal = await_delivery(store, provider, DeliveryState(status))
        if status in {"delivered", "read"}:
            assert post_signed(client, provider, status="sent").status_code == 200
            assert (
                store.get_delivery_for_inbound(accepted.inbound_message_id).state == terminal.state
            )
        assert len(store.get_history(provider=provider, customer_address=customer)) == 2

    reopened = SqliteConversationStore(settings.database_path)
    with TestClient(app_for(reopened)) as client:
        assert post_signed(client, provider).status_code == 200
        assert client.app.state.processing_executor.run_once() is None
        assert (
            OutboundDeliveryRunner(
                store=reopened, sender=sender, timeout_seconds=2, provider=provider
            ).run_once()
            is None
        )
        assert reopened.get_delivery_for_inbound(accepted.inbound_message_id) == terminal
    assert len(model_calls) == len(outbound_calls) == 1
    body = outbound_calls[0]["body"] if provider == "twilio" else outbound_calls[0]["text"]["body"]
    assert body == accepted.body


@pytest.mark.parametrize("provider", ["twilio", "meta"])
def test_ambiguous_real_adapter_transport_never_resends_after_restart(tmp_path, provider):
    settings, store, generator, sender, model_calls, outbound_calls = controlled_pipeline(
        tmp_path, provider, unknown=True
    )
    with TestClient(
        create_app(settings, store=store, generator=generator, outbound_sender=sender)
    ) as client:
        assert post_signed(client, provider).status_code == 200
        unknown = await_delivery(store, provider, DeliveryState.UNKNOWN)
        assert unknown.provider_message_id is None
    reopened = SqliteConversationStore(settings.database_path)
    with TestClient(
        create_app(settings, store=reopened, generator=generator, outbound_sender=sender)
    ) as client:
        assert post_signed(client, provider).status_code == 200
        assert (
            OutboundDeliveryRunner(
                store=reopened, sender=sender, timeout_seconds=2, provider=provider
            ).run_once()
            is None
        )
        assert client.app.state.processing_executor.run_once() is None
        assert reopened.get_delivery_for_inbound(unknown.inbound_message_id) == unknown
    assert len(model_calls) == len(outbound_calls) == 1


@pytest.mark.parametrize("provider", ["twilio", "meta"])
def test_signed_status_before_correlation_survives_restart_and_reconciles(tmp_path, provider):
    settings, store, generator, sender, model_calls, outbound_calls = controlled_pipeline(
        tmp_path, provider
    )
    with TestClient(
        create_app(settings, store=store, generator=generator, outbound_sender=sender)
    ) as client:
        assert post_signed(client, provider, status="read").status_code == 200
    reopened = SqliteConversationStore(settings.database_path)
    with TestClient(
        create_app(settings, store=reopened, generator=generator, outbound_sender=sender)
    ) as client:
        assert post_signed(client, provider).status_code == 200
        delivery = await_delivery(reopened, provider, DeliveryState.READ)
        assert post_signed(client, provider, status="sent").status_code == 200
        assert (
            reopened.get_delivery_for_inbound(delivery.inbound_message_id).state
            == DeliveryState.READ
        )
    assert len(model_calls) == len(outbound_calls) == 1
