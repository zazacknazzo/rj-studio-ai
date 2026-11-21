"""Dormant offline Telnyx sender. Only an injected, intercepted exchange is supported."""

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.providers.base import (
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    ProviderAcceptance,
)
from rj_studio_ai.telnyx_request import InvalidTelnyxRequest, TelnyxRequest, TelnyxRequestSigner


@dataclass(frozen=True, slots=True, repr=False)
class TelnyxHttpResponse:
    status_code: int
    content: bytes
    content_type: str = "application/json"


class InterceptedTelnyxExchange(Protocol):
    """Trusted offline injection; no retries, redirects, credentials or default client.

    Implementations must honor the supplied budgets and invoke no external API.
    This protocol specifies transport behavior; it cannot sandbox arbitrary callables.
    """

    def __call__(
        self,
        request: TelnyxRequest,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        retries: Literal[0],
        follow_redirects: Literal[False],
    ) -> TelnyxHttpResponse: ...


class TelnyxOutcomeUnknown(OutboundOutcomeUnknown):
    """Only a fixed safe classification escapes the untrusted response boundary."""

    def __init__(self, reason: str) -> None:
        self.safe_error_code = reason
        super().__init__(reason)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError("Nonstandard JSON constant")


def _optional_schema_valid(data: dict, recipient: dict, body: dict) -> bool:
    sender = data["from"]
    if "status" in sender and sender["status"] not in ("received", "delivered"):
        return False
    if "line_type" in sender and sender["line_type"] not in (
        "Wireline",
        "Wireless",
        "VoWiFi",
        "VoIP",
        "Pre-Paid Wireless",
        "",
    ):
        return False
    for parent, names in (
        (sender, ("carrier",)),
        (recipient, ("carrier", "line_type")),
        (data, ("encoding",)),
        (body, ("biz_opaque_callback_data",)),
    ):
        if any(name in parent and not isinstance(parent[name], str) for name in names):
            return False
    if "received_at" in data:
        value = data["received_at"]
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value,
        ):
            return False
        if datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
            return False
    if "wait_seconds" in data and data["wait_seconds"] is not None:
        value = data["wait_seconds"]
        if type(value) not in (int, float) or not math.isfinite(value):
            return False
    # Valid JSON can still contradict the requested text modality. Unknown new
    # fields remain forward compatible; known alternative message bodies do not.
    return not {
        "audio",
        "document",
        "image",
        "sticker",
        "video",
        "interactive",
        "location",
        "contacts",
        "reaction",
        "template",
    }.intersection(body)


def _parse_response(response: TelnyxHttpResponse, request: TelnyxRequest) -> ProviderAcceptance:
    if not isinstance(response.content, bytes) or len(response.content) > 1_048_576:
        raise TelnyxOutcomeUnknown("telnyx_response_invalid")
    try:
        payload = json.loads(
            response.content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError
        errors = payload.get("errors")
        code = (
            errors[0].get("code")
            if isinstance(errors, list) and len(errors) == 1 and isinstance(errors[0], dict)
            else None
        )
        if response.status_code == 409 and code == "10036":
            raise TelnyxOutcomeUnknown("telnyx_in_progress")
        if response.status_code == 422 and code == "10027":
            raise TelnyxOutcomeUnknown("telnyx_key_conflict")
        # The endpoint documents 200, not an arbitrary successful status contract.
        if response.status_code != 200:
            raise TelnyxOutcomeUnknown("telnyx_http_unknown")
        if response.content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError
        data = payload["data"]
        recipients = data["to"]
        body = data["body"]
        if not (
            data["record_type"] == "message"
            and data["direction"] == "outbound"
            and data["type"] == "WHATSAPP"
            and data["organization_id"] == request.organization_id
            and data["messaging_profile_id"] == request.profile_id
            and data["from"]["phone_number"] == request.message.sender_address
            and isinstance(recipients, list)
            and len(recipients) == 1
            and recipients[0]["phone_number"] == request.message.recipient_address
            and recipients[0]["status"] in {"queued", "sending", "sent", "delivered", "read"}
            and _optional_schema_valid(data, recipients[0], body)
            and body["type"] == "text"
            and body["text"]["body"] == request.message.body
            and body["text"].get("preview_url", False) is False
            and data.get("cc", []) == []
            and data.get("errors", []) == []
            and payload.get("errors", []) == []
            and "origin" not in data
            and isinstance(data["id"], str)
            and re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", data["id"])
        ):
            raise ValueError
        return ProviderAcceptance(data["id"])
    except (KeyError, ValueError, TypeError, AttributeError, IndexError, RecursionError):
        raise TelnyxOutcomeUnknown("telnyx_response_invalid") from None


@dataclass(frozen=True, slots=True, repr=False)
class TelnyxWhatsAppSender(OutboundMessageSender):
    signer: TelnyxRequestSigner
    exchange: InterceptedTelnyxExchange

    def prepare(self, message: OutboundMessage) -> TelnyxRequest:
        return self.signer.prepare(message)

    def send(self, message: OutboundMessage, *, timeout_seconds: float) -> ProviderAcceptance:
        # The runner must bind the exact prepared request in the store first.
        raise InvalidTelnyxRequest("Prepared Telnyx authorization required")

    def send_prepared(
        self,
        request: TelnyxRequest,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        """Caller must have committed store authorization for this exact request.

        Low-level adapter seam, not authorization or operational composition. The
        runner calls it once; reusing a key never authorizes invoking it again.
        """
        if not (math.isfinite(timeout_seconds) and timeout_seconds > 0):
            raise InvalidTelnyxRequest("Invalid offline Telnyx timeout")
        connect_timeout = timeout_seconds / 3
        read_timeout = timeout_seconds - connect_timeout
        if connect_timeout <= 0 or read_timeout <= 0:
            raise InvalidTelnyxRequest("Invalid offline Telnyx timeout")
        if not self.signer.verify(request):
            raise InvalidTelnyxRequest("Invalid offline Telnyx request")
        try:
            response = self.exchange(
                request,
                connect_timeout_seconds=connect_timeout,
                read_timeout_seconds=read_timeout,
                retries=0,
                follow_redirects=False,
            )
        except Exception:
            # Includes connection timeout: this callable provides no proof that
            # bytes were not transmitted. Never expose its exception or retry.
            raise TelnyxOutcomeUnknown("telnyx_transport_unknown") from None
        try:
            return _parse_response(response, request)
        except TelnyxOutcomeUnknown:
            raise
        except Exception:
            raise TelnyxOutcomeUnknown("telnyx_response_invalid") from None
