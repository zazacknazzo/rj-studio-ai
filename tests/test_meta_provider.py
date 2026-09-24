import hashlib
import hmac
import json
from dataclasses import dataclass

import pytest
from requests import ConnectionError as RequestsConnectionError
from requests import Timeout as RequestsTimeout

from rj_studio_ai.domain import (
    DeliveryStatus,
    DeliveryStatusReceived,
    InboundMessageReceived,
    OutboundMessage,
)
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
    ProviderWebhookRequest,
)
from rj_studio_ai.providers.meta import MetaOutboundMessageSender, MetaProvider

APP_SECRET = "meta-app-secret"
ACCESS_TOKEN = "meta-access-token"
PHONE_NUMBER_ID = "123456789012345"
INBOUND_WAMID = "wamid.inbound-synthetic"
OUTBOUND_WAMID = "wamid.outbound-synthetic"


def _payload(*, include_unsupported: bool = False) -> dict[str, object]:
    messages: list[dict[str, object]] = [
        {
            "from": "5511999999999",
            "id": INBOUND_WAMID,
            "timestamp": "1790000000",
            "type": "text",
            "text": {"body": "Mensagem sintética"},
        }
    ]
    if include_unsupported:
        messages.insert(
            0,
            {
                "from": "5511888888888",
                "id": "wamid.image-synthetic",
                "timestamp": "1790000001",
                "type": "image",
                "image": {"id": "media-synthetic"},
            },
        )
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
                            "messages": messages,
                            "statuses": [
                                {
                                    "id": OUTBOUND_WAMID,
                                    "status": "delivered",
                                    "timestamp": "1790000002",
                                    "recipient_id": "5511999999999",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _request(payload: dict[str, object], *, signature: str | None = None) -> ProviderWebhookRequest:
    body = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return ProviderWebhookRequest(
        method="POST",
        url="https://example.test/webhooks/meta",
        headers={"x-hub-signature-256": signature or f"sha256={digest}"},
        query_string=b"",
        content_type="application/json; charset=utf-8",
        body=body,
    )


def test_meta_adapter_authenticates_and_translates_mixed_supported_batch() -> None:
    adapter = MetaProvider(verify_token="verify-token", app_secret=APP_SECRET)

    batch = adapter.receive(_request(_payload(include_unsupported=True)))

    assert batch.events == (
        InboundMessageReceived(
            provider="meta",
            provider_message_id=INBOUND_WAMID,
            customer_address="5511999999999",
            recipient_address=PHONE_NUMBER_ID,
            body="Mensagem sintética",
        ),
        DeliveryStatusReceived(
            provider="meta",
            provider_message_id=OUTBOUND_WAMID,
            status=DeliveryStatus.DELIVERED,
        ),
    )


def test_meta_adapter_rejects_invalid_signature_before_parsing() -> None:
    adapter = MetaProvider(verify_token="verify-token", app_secret=APP_SECRET)

    with pytest.raises(InvalidWebhookSignature):
        adapter.receive(_request(_payload(), signature="sha256=" + "0" * 64))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"object": "not-whatsapp", "entry": []},
        {"object": "whatsapp_business_account", "entry": "invalid"},
    ],
)
def test_meta_adapter_rejects_invalid_envelope(payload: dict[str, object]) -> None:
    adapter = MetaProvider(verify_token="verify-token", app_secret=APP_SECRET)

    with pytest.raises(InvalidWebhookPayload):
        adapter.receive(_request(payload))


@pytest.mark.parametrize(
    ("provider_status", "canonical_status", "safe_error_code"),
    [
        ("sent", DeliveryStatus.SENT, None),
        ("delivered", DeliveryStatus.DELIVERED, None),
        ("read", DeliveryStatus.READ, None),
        ("failed", DeliveryStatus.FAILED, "provider_failed"),
    ],
)
def test_meta_adapter_normalizes_delivery_statuses(
    provider_status: str,
    canonical_status: DeliveryStatus,
    safe_error_code: str | None,
) -> None:
    payload = _payload()
    payload["entry"][0]["changes"][0]["value"].pop("messages")  # type: ignore[index]
    payload["entry"][0]["changes"][0]["value"]["statuses"][0]["status"] = (  # type: ignore[index]
        provider_status
    )
    adapter = MetaProvider(verify_token="verify-token", app_secret=APP_SECRET)

    assert adapter.receive(_request(payload)).events == (
        DeliveryStatusReceived(
            provider="meta",
            provider_message_id=OUTBOUND_WAMID,
            status=canonical_status,
            safe_error_code=safe_error_code,
        ),
    )


def test_meta_adapter_ignores_irrelevant_changes() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba-synthetic", "changes": [{"field": "account_update"}]}],
    }
    adapter = MetaProvider(verify_token="verify-token", app_secret=APP_SECRET)

    assert adapter.receive(_request(payload)).events == ()


@dataclass
class _Response:
    status_code: int
    payload: object

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _RecordingPost:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def __call__(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.result, Exception):
            raise self.result
        assert isinstance(self.result, _Response)
        return self.result


def _sender(
    result: object,
    *,
    eligible: bool = True,
) -> tuple[MetaOutboundMessageSender, _RecordingPost]:
    post = _RecordingPost(result)
    return (
        MetaOutboundMessageSender(
            access_token=ACCESS_TOKEN,
            phone_number_id=PHONE_NUMBER_ID,
            api_version="v24.0",
            free_form_is_eligible=lambda _: eligible,
            post=post,
        ),
        post,
    )


def _outbound() -> OutboundMessage:
    return OutboundMessage(
        sender_address=PHONE_NUMBER_ID,
        recipient_address="5511999999999",
        body="Resposta sintética",
    )


def test_meta_sender_maps_proven_success_to_provider_acceptance() -> None:
    sender, post = _sender(
        _Response(200, {"messaging_product": "whatsapp", "messages": [{"id": OUTBOUND_WAMID}]})
    )

    result = sender.send(_outbound(), timeout_seconds=4.0)

    assert result == ProviderAcceptance(provider_message_id=OUTBOUND_WAMID)
    assert post.calls == [
        {
            "url": f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages",
            "headers": {
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            "json": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": "5511999999999",
                "type": "text",
                "text": {"preview_url": False, "body": "Resposta sintética"},
            },
            "timeout": 4.0,
        }
    ]


def test_meta_sender_fails_closed_before_network_outside_service_window() -> None:
    sender, post = _sender(_Response(200, {}), eligible=False)

    with pytest.raises(OutboundPermanentError, match="meta_free_form_not_eligible"):
        sender.send(_outbound(), timeout_seconds=2.0)

    assert post.calls == []


@pytest.mark.parametrize(
    ("result", "expected", "code"),
    [
        (
            _Response(429, {"error": {"code": 4, "is_transient": True}}),
            OutboundRetryableError,
            "meta_rate_limited",
        ),
        (
            _Response(400, {"error": {"code": 190, "is_transient": False}}),
            OutboundPermanentError,
            "meta_request_rejected",
        ),
        (
            _Response(500, {"error": {"code": 2}}),
            OutboundOutcomeUnknown,
            "meta_outcome_unknown",
        ),
        (RequestsTimeout("meta-access-token"), OutboundOutcomeUnknown, "meta_outcome_unknown"),
        (
            RequestsConnectionError("5511999999999"),
            OutboundOutcomeUnknown,
            "meta_outcome_unknown",
        ),
        (_Response(200, ValueError("bad json")), OutboundOutcomeUnknown, "meta_response_ambiguous"),
    ],
)
def test_meta_sender_classifies_failures_without_leaking_secrets_or_pii(
    result: object,
    expected: type[Exception],
    code: str,
) -> None:
    sender, _ = _sender(result)

    with pytest.raises(expected, match=code) as caught:
        sender.send(_outbound(), timeout_seconds=2.0)

    diagnostic = str(caught.value)
    assert ACCESS_TOKEN not in diagnostic
    assert "5511999999999" not in diagnostic
