from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from requests import ConnectionError as RequestsConnectionError
from requests import Timeout as RequestsTimeout
from twilio.base.exceptions import TwilioRestException

from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import InboundMessage, OutboundMessage
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import (
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
)
from rj_studio_ai.providers.twilio import TwilioOutboundSender

ACCOUNT_SID = "AC" + "1" * 32
API_KEY_SID = "SK" + "2" * 32
MESSAGE_SID = "SM" + "3" * 32
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


@dataclass
class _CreatedMessage:
    sid: str
    status: str


class _RecordingMessages:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, str]] = []

    def create(self, **kwargs: str) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _RecordingClient:
    def __init__(self, messages: _RecordingMessages) -> None:
        self.messages = messages


def _sender(
    outcome: object,
) -> tuple[TwilioOutboundSender, _RecordingMessages, list[float]]:
    messages = _RecordingMessages(outcome)
    timeouts: list[float] = []

    def factory(timeout_seconds: float) -> Any:
        timeouts.append(timeout_seconds)
        return _RecordingClient(messages)

    return (
        TwilioOutboundSender(
            account_sid=ACCOUNT_SID,
            api_key_sid=API_KEY_SID,
            api_key_secret="api-secret-value",
            status_callback_url="https://example.test/webhooks/twilio/status",
            client_factory=factory,
        ),
        messages,
        timeouts,
    )


@pytest.mark.parametrize("initial_status", ["queued", "accepted"])
def test_twilio_sender_maps_successful_create_to_provider_acceptance(
    initial_status: str,
) -> None:
    sender, messages, timeouts = _sender(_CreatedMessage(sid=MESSAGE_SID, status=initial_status))
    outbound = OutboundMessage(
        sender_address="whatsapp:+14155238886",
        recipient_address="whatsapp:+5511999999999",
        body="Mensagem sintética",
    )

    result = sender.send(outbound, timeout_seconds=4.5)

    assert result == ProviderAcceptance(provider_message_id=MESSAGE_SID)
    assert timeouts == [4.5]
    assert messages.calls == [
        {
            "from_": "whatsapp:+14155238886",
            "to": "whatsapp:+5511999999999",
            "body": "Mensagem sintética",
            "status_callback": "https://example.test/webhooks/twilio/status",
        }
    ]


def test_twilio_sender_treats_invalid_or_missing_message_sid_as_unknown() -> None:
    sender, _, _ = _sender(_CreatedMessage(sid="not-a-message-sid", status="queued"))

    with pytest.raises(OutboundOutcomeUnknown, match="twilio_response_ambiguous"):
        sender.send(
            OutboundMessage(
                sender_address="whatsapp:+14155238886",
                recipient_address="whatsapp:+5511999999999",
                body="Mensagem sintética",
            ),
            timeout_seconds=2.0,
        )


def test_twilio_sender_rejects_invalid_local_configuration_before_network() -> None:
    messages = _RecordingMessages(_CreatedMessage(sid=MESSAGE_SID, status="queued"))
    sender = TwilioOutboundSender(
        account_sid="not-an-account-sid",
        api_key_sid=API_KEY_SID,
        api_key_secret="api-secret-value",
        status_callback_url="https://invalid_host.example/status",
        client_factory=lambda _: _RecordingClient(messages),
    )

    assert not sender.is_configured()
    with pytest.raises(OutboundPermanentError, match="twilio_not_configured"):
        sender.send(
            OutboundMessage(
                sender_address="whatsapp:+14155238886",
                recipient_address="whatsapp:+5511999999999",
                body="Mensagem sintética",
            ),
            timeout_seconds=2.0,
        )
    assert messages.calls == []


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            TwilioRestException(429, "/Messages", "rate limited", code=20429),
            OutboundRetryableError,
        ),
        (
            TwilioRestException(400, "/Messages", "invalid recipient", code=21211),
            OutboundPermanentError,
        ),
        (
            TwilioRestException(401, "/Messages", "bad credential", code=20003),
            OutboundPermanentError,
        ),
        (
            TwilioRestException(500, "/Messages", "internal error", code=20500),
            OutboundOutcomeUnknown,
        ),
        (
            TwilioRestException(408, "/Messages", "request timeout", code=20408),
            OutboundOutcomeUnknown,
        ),
        (
            TwilioRestException(409, "/Messages", "conflict", code=20409),
            OutboundOutcomeUnknown,
        ),
        (
            TwilioRestException(422, "/Messages", "undocumented rejection", code=29999),
            OutboundOutcomeUnknown,
        ),
        (RequestsTimeout("api-secret-value"), OutboundOutcomeUnknown),
        (RequestsConnectionError("api-secret-value"), OutboundOutcomeUnknown),
    ],
)
def test_twilio_sender_classifies_errors_without_leaking_provider_details(
    failure: Exception,
    expected: type[Exception],
) -> None:
    sender, _, _ = _sender(failure)

    with pytest.raises(expected) as caught:
        sender.send(
            OutboundMessage(
                sender_address="whatsapp:+14155238886",
                recipient_address="whatsapp:+5511999999999",
                body="Mensagem sintética",
            ),
            timeout_seconds=2.0,
        )

    assert "api-secret-value" not in str(caught.value)
    assert "invalid recipient" not in str(caught.value)


def test_delivery_runner_persists_twilio_provider_acceptance(tmp_path: Path) -> None:
    store = SqliteConversationStore(tmp_path / "twilio-runner.db")
    store.initialize()
    claim = store.claim_generation(
        InboundMessage(
            provider="twilio",
            provider_message_id="SM-runner-inbound",
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
    sender, _, _ = _sender(_CreatedMessage(sid=MESSAGE_SID, status="queued"))

    delivery = OutboundDeliveryRunner(
        store=store,
        sender=sender,
        timeout_seconds=2.0,
    ).run_once(now=NOW + timedelta(seconds=2))

    assert delivery is not None
    assert delivery.state is DeliveryState.ACCEPTED
    assert delivery.provider_message_id == MESSAGE_SID
    assert delivery.accepted_at == NOW + timedelta(seconds=2)
    metric = store.get_delivery_metric(delivery.delivery_id)
    assert metric is not None
    assert metric.provider == "twilio"
    assert metric.state is DeliveryState.ACCEPTED
    assert metric.attempt_count == 1
    assert metric.acceptance_latency_ms == 2_000
    assert metric.latest_attempt_latency_ms == 0
    assert not hasattr(metric, "body")
    assert not hasattr(metric, "recipient_address")
