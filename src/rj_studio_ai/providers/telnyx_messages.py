"""Dormant authenticated Telnyx Message parsing; no runtime factory or sending."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime

from rj_studio_ai.config import Settings
from rj_studio_ai.domain import (
    EventOrigin,
    HumanMessageObserved,
    InboundMessageReceived,
    MessageEdited,
    MessageReference,
    MessageRevoked,
    ProviderEventMetadata,
    ProviderWebhookEventBatch,
)
from rj_studio_ai.providers.base import (
    InboundWebhookAdapter,
    InvalidWebhookPayload,
    ProviderWebhookRequest,
    ProviderWebhookResponse,
)
from rj_studio_ai.providers.telnyx import TelnyxWebhookAuthenticator


def _identifier(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or any(character.isspace() or ord(character) < 32 for character in value)
        or not value.isascii()
    ):
        raise ValueError("Invalid identifier")
    return value


def _phone(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"\+[1-9][0-9]{1,14}", value) is not None


def _customer(address: object, body: dict) -> str:
    # body.from is a customer in BOTH documented envelopes, never direction evidence.
    body_from = body.get("from")
    opaque = body.get("from_user_id")
    if opaque is not None:
        _identifier(opaque)
    if _phone(address):
        if body_from not in (None, "", address):
            raise ValueError("Contradictory customer")
        return address
    if body_from not in (None, "") or opaque is None or address not in (None, "", opaque):
        raise ValueError("Unresolved customer")
    # Namespace the opaque address so even a phone-shaped BSUID cannot merge identities.
    return "bsuid:" + _identifier(opaque)


def _event_time(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        raise ValueError("Invalid event time")
    return datetime.fromisoformat(value).astimezone(UTC)


def _source_time(value: object, occurred_at: datetime, received_at: datetime) -> datetime | None:
    # No fallback to envelope time, signature time, received_at or local wall time.
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}", value):
        return None
    try:
        source = datetime.fromtimestamp(int(value), UTC)
    except (ValueError, OverflowError, OSError):
        return None
    return source if source <= occurred_at <= received_at else None


class TelnyxMessageAdapter(InboundWebhookAdapter):
    """Only Ticket 07 contracts; unsupported callbacks raise, never empty-success."""

    def __init__(self, settings: Settings, *, clock: Callable[[], float]) -> None:
        self._authenticator = TelnyxWebhookAuthenticator(settings, clock=clock)
        self._clock = clock

    def is_configured(self) -> bool:
        # Local ingress configuration only, not channel or delivery readiness.
        return True

    def receive(self, webhook: ProviderWebhookRequest) -> ProviderWebhookEventBatch:
        raw = self._authenticator.authenticate(webhook)
        try:
            data = json.loads(raw)["data"]
            event_type = data["event_type"]
            if event_type not in ("message.received", "message.echo"):
                raise ValueError("Unsupported event")
            payload = data["payload"]
            echo = event_type == "message.echo"
            if echo and payload.get("origin") != "whatsapp_business_app":
                raise ValueError("Invalid echo origin")
            message_id = _identifier(payload["id"])
            body = payload["body"]
            if not isinstance(body, dict):
                raise ValueError("Invalid body")
            if "id" in body and body["id"] != message_id:
                raise ValueError("Contradictory message identity")
            customer = _customer(payload["to"] if echo else payload["from"]["phone_number"], body)
            channel = payload["from"]["phone_number"] if echo else payload["to"]
            if customer == channel:
                raise ValueError("Ambiguous customer")
            occurred_at = _event_time(data["occurred_at"])
            aliases = (
                (MessageReference("meta", _identifier(body["foreign_id"])),)
                if "foreign_id" in body
                else ()
            )
            metadata = ProviderEventMetadata(
                event_id=_identifier(data["id"]),
                origin=EventOrigin.HUMAN_OPERATOR if echo else EventOrigin.CUSTOMER,
                occurred_at=occurred_at,
                message_aliases=aliases,
                message_occurred_at=_source_time(
                    body.get("timestamp"), occurred_at, datetime.fromtimestamp(self._clock(), UTC)
                ),
            )
            if echo:
                event = HumanMessageObserved("telnyx", message_id, channel, customer, metadata)
            elif body.get("type") in ("edit", "revoke"):
                kind = body["type"]
                change = body[kind]
                original = MessageReference(
                    "telnyx_original_opaque", _identifier(change["original_message_id"])
                )
                if kind == "edit" and not isinstance(change["message"], dict):
                    raise ValueError("Invalid edit")
                event = (MessageEdited if kind == "edit" else MessageRevoked)(
                    "telnyx", message_id, channel, customer, original, metadata
                )
            elif body.get("type") == "text":
                text = body["text"]["body"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Invalid text")
                # Reject unpaired JSON surrogates before SQLite encoding can fail.
                text.encode("utf-8")
                event = InboundMessageReceived(
                    "telnyx", message_id, customer, channel, text, metadata=metadata
                )
            else:
                raise ValueError("Unsupported content")
            return ProviderWebhookEventBatch((event,))
        except (ValueError, KeyError, TypeError, OverflowError, OSError):
            raise InvalidWebhookPayload("Invalid or unsupported Telnyx Message event") from None

    def acknowledge(self) -> ProviderWebhookResponse:
        return ProviderWebhookResponse("", "application/json", 204)
