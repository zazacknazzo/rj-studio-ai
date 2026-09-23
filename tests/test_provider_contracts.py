from typing import get_type_hints
from urllib.parse import urlencode

import pytest
from twilio.request_validator import RequestValidator

from rj_studio_ai.domain import (
    AIReply,
    DeliveryStatus,
    DeliveryStatusReceived,
    InboundMessageReceived,
    OutboundMessage,
    ProviderWebhookEventBatch,
)
from rj_studio_ai.providers.base import (
    InboundWebhookAdapter,
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
    ProviderWebhookRequest,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.providers.twilio import TwilioProvider


def _twilio_request(**overrides: str) -> ProviderWebhookRequest:
    form = {
        "MessageSid": "SM-contract-message",
        "From": "whatsapp:+5511999999999",
        "To": "whatsapp:+14155238886",
        "Body": "Mensagem de contrato",
        **overrides,
    }
    return ProviderWebhookRequest(
        method="POST",
        url="https://example.test/webhooks/twilio",
        headers={},
        query_string=b"",
        content_type="application/x-www-form-urlencoded",
        body=urlencode(form).encode(),
    )


def test_twilio_translates_inbound_to_a_canonical_event() -> None:
    adapter: InboundWebhookAdapter = TwilioProvider(
        auth_token="",
        validate_signature=False,
        public_webhook_url=None,
    )

    batch = adapter.receive(_twilio_request())

    assert batch.events == (
        InboundMessageReceived(
            provider="twilio",
            provider_message_id="SM-contract-message",
            customer_address="whatsapp:+5511999999999",
            recipient_address="whatsapp:+14155238886",
            body="Mensagem de contrato",
        ),
    )


def test_delivery_status_event_is_provider_neutral() -> None:
    event = DeliveryStatusReceived(
        provider="provider-name",
        provider_message_id="provider-message-id",
        status=DeliveryStatus.DELIVERED,
    )

    assert event.provider == "provider-name"
    assert event.provider_message_id == "provider-message-id"
    assert event.status is DeliveryStatus.DELIVERED


def test_canonical_batch_can_hold_inbound_and_status_events() -> None:
    inbound = InboundMessageReceived(
        provider="provider-name",
        provider_message_id="inbound-1",
        customer_address="customer-1",
        recipient_address="studio",
        body="Olá",
    )
    status = DeliveryStatusReceived(
        provider="provider-name",
        provider_message_id="outbound-1",
        status=DeliveryStatus.SENT,
    )

    batch = ProviderWebhookEventBatch(events=(inbound, status))

    assert batch.events == (inbound, status)


def test_public_contract_annotations_use_only_canonical_types() -> None:
    inbound_hints = get_type_hints(InboundWebhookAdapter.receive)
    outbound_hints = get_type_hints(OutboundMessageSender.send)

    assert inbound_hints["webhook"] is ProviderWebhookRequest
    assert "twilio" not in repr(inbound_hints["return"]).lower()
    assert outbound_hints["message"] is OutboundMessage
    assert outbound_hints["return"] is ProviderAcceptance


def test_acknowledgement_is_distinct_from_legacy_customer_reply() -> None:
    adapter = TwilioProvider(
        auth_token="",
        validate_signature=False,
        public_webhook_url=None,
    )

    acknowledgement = adapter.acknowledge()
    legacy_reply = adapter.render_legacy_reply(AIReply(body="Resposta atual"))

    assert acknowledgement.status_code == 200
    assert "<Message>" not in acknowledgement.body
    assert "Resposta atual" not in acknowledgement.body
    assert "<Message>Resposta atual</Message>" in legacy_reply.body


def test_invalid_twilio_event_uses_provider_neutral_payload_error() -> None:
    adapter: InboundWebhookAdapter = TwilioProvider(
        auth_token="",
        validate_signature=False,
        public_webhook_url=None,
    )

    with pytest.raises(InvalidWebhookPayload):
        adapter.receive(_twilio_request(Body=""))


@pytest.mark.parametrize(
    ("form", "expected_status", "expected_error"),
    [
        ({"MessageStatus": "sent"}, DeliveryStatus.SENT, None),
        ({"MessageStatus": "delivered"}, DeliveryStatus.DELIVERED, None),
        ({"MessageStatus": "read"}, DeliveryStatus.READ, None),
        (
            {"MessageStatus": "delivered", "EventType": "READ"},
            DeliveryStatus.READ,
            None,
        ),
        ({"MessageStatus": "failed"}, DeliveryStatus.FAILED, "provider_failed"),
        (
            {"MessageStatus": "undelivered"},
            DeliveryStatus.FAILED,
            "provider_undelivered",
        ),
    ],
)
def test_twilio_translates_status_callbacks_to_canonical_events(
    form: dict[str, str],
    expected_status: DeliveryStatus,
    expected_error: str | None,
) -> None:
    adapter = TwilioProvider(
        auth_token="",
        validate_signature=False,
        public_webhook_url=None,
        public_status_callback_url=None,
    )
    request = _twilio_request(
        MessageSid="SM" + "1" * 32,
        From="",
        To="",
        Body="",
        ExtraParameter="ignored",
        **form,
    )

    batch = adapter.receive(request)

    assert batch.events == (
        DeliveryStatusReceived(
            provider="twilio",
            provider_message_id="SM" + "1" * 32,
            status=expected_status,
            safe_error_code=expected_error,
        ),
    )


@pytest.mark.parametrize("status", ["queued", "sending", "accepted", "future-status"])
def test_twilio_acknowledges_statuses_that_do_not_change_canonical_state(status: str) -> None:
    adapter = TwilioProvider(
        auth_token="",
        validate_signature=False,
        public_webhook_url=None,
        public_status_callback_url=None,
    )

    batch = adapter.receive(
        _twilio_request(
            MessageSid="SM" + "1" * 32,
            From="",
            To="",
            Body="",
            MessageStatus=status,
        )
    )

    assert batch.events == ()


def test_twilio_status_signature_uses_status_callback_url_and_all_parameters() -> None:
    auth_token = "status-signature-secret"
    public_url = "https://public.example/webhooks/twilio/status"
    form = {
        "MessageSid": "SM" + "1" * 32,
        "MessageStatus": "delivered",
        "ExtraParameter": "included-in-signature",
    }
    signature = RequestValidator(auth_token).compute_signature(public_url, form)
    adapter = TwilioProvider(
        auth_token=auth_token,
        validate_signature=True,
        public_webhook_url="https://public.example/webhooks/twilio",
        public_status_callback_url=public_url,
    )
    request = ProviderWebhookRequest(
        method="POST",
        url="http://internal/webhooks/twilio/status",
        headers={"x-twilio-signature": signature},
        query_string=b"",
        content_type="application/x-www-form-urlencoded",
        body=urlencode(form).encode(),
    )

    assert adapter.receive(request).events[0].status is DeliveryStatus.DELIVERED

    invalid = ProviderWebhookRequest(
        method=request.method,
        url=request.url,
        headers={"x-twilio-signature": "invalid"},
        query_string=request.query_string,
        content_type=request.content_type,
        body=request.body,
    )
    with pytest.raises(InvalidWebhookSignature):
        adapter.receive(invalid)


def test_fake_sender_returns_canonical_acceptance_and_records_the_call() -> None:
    accepted = ProviderAcceptance(provider_message_id="provider-outbound-1")
    sender: OutboundMessageSender = DeterministicFakeOutboundSender(outcomes=[accepted])
    message = OutboundMessage(
        sender_address="studio-channel",
        recipient_address="customer-1",
        body="Olá",
    )

    result = sender.send(message, timeout_seconds=2.5)

    assert result == accepted
    assert sender.calls == [(message, 2.5)]


@pytest.mark.parametrize(
    "failure",
    [
        OutboundRetryableError("provider proved non-acceptance"),
        OutboundPermanentError("provider rejected the message"),
        OutboundOutcomeUnknown("provider outcome is ambiguous"),
    ],
)
def test_fake_sender_raises_programmed_provider_neutral_failure(
    failure: Exception,
) -> None:
    sender: OutboundMessageSender = DeterministicFakeOutboundSender(outcomes=[failure])
    message = OutboundMessage(
        sender_address="studio-channel",
        recipient_address="customer-1",
        body="Olá",
    )

    with pytest.raises(type(failure), match=str(failure)):
        sender.send(message, timeout_seconds=1.0)

    assert sender.calls == [(message, 1.0)]


def test_fake_sender_requires_an_explicit_outcome_for_each_call() -> None:
    sender = DeterministicFakeOutboundSender(outcomes=[])

    with pytest.raises(AssertionError, match="No programmed outbound outcome"):
        sender.send(
            OutboundMessage(
                sender_address="studio-channel",
                recipient_address="customer-1",
                body="Olá",
            ),
            timeout_seconds=1.0,
        )


def test_fake_sender_rejects_a_failure_outside_the_contract() -> None:
    with pytest.raises(TypeError, match="Unsupported outbound outcome"):
        DeterministicFakeOutboundSender(outcomes=[RuntimeError("unexpected")])
