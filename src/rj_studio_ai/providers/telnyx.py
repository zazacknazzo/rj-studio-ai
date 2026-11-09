"""Dormant Telnyx ingress authentication; no canonical parsing, ACK or sending."""

import base64
import binascii
import json
import math
import re
import time
from collections.abc import Callable

from nacl.bindings import crypto_core_ed25519_is_valid_point
from nacl.exceptions import CryptoError
from nacl.signing import VerifyKey

from rj_studio_ai.config import Settings
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    ProviderWebhookRequest,
)


class TelnyxConfigurationError(ValueError):
    """Local ingress configuration is incomplete or invalid; never includes inputs."""


def _decode_base64(value: str, length: int) -> bytes:
    # Bound decoding and disallow whitespace, non-ASCII, padding aliases and junk.
    if not isinstance(value, str) or len(value) != 4 * ((length + 2) // 3):
        raise ValueError("Invalid encoded value")
    decoded = base64.b64decode(value, validate=True)
    if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("Invalid encoded value")
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous JSON")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant")


class TelnyxWebhookAuthenticator:
    """Authenticate exact request bytes and check scope, without operational effects.

    Successful construction proves local ingress configuration only. This is not
    an InboundWebhookAdapter or a sender and cannot make runtime readiness true.
    Business parsing and persistence-before-ACK belong to subsequent tickets.
    """

    def __init__(self, settings: Settings, *, clock: Callable[[], float] = time.time) -> None:
        try:
            raw_key = _decode_base64(settings.telnyx_public_key, 32)
            # Length alone admits degenerate keys that can validate forgeries.
            # libsodium checks canonical encoding, curve, subgroup and small order.
            if not crypto_core_ed25519_is_valid_point(raw_key):
                raise ValueError("Invalid public key")
            key = VerifyKey(raw_key)
        except (ValueError, TypeError, binascii.Error, CryptoError):
            raise TelnyxConfigurationError("Invalid Telnyx ingress configuration") from None
        if (
            settings.delivery_mode != "proactive"
            or not re.fullmatch(r"\+[1-9][0-9]{1,14}", settings.telnyx_phone_number)
            or not all(
                re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
                for value in (
                    settings.telnyx_messaging_profile_id,
                    settings.telnyx_waba_id,
                    settings.telnyx_organization_id,
                )
            )
            or type(settings.telnyx_webhook_max_body_bytes) is not int
            or not 1 <= settings.telnyx_webhook_max_body_bytes <= 1_048_576
            or type(settings.telnyx_webhook_tolerance_seconds) is not int
            or not 1 <= settings.telnyx_webhook_tolerance_seconds <= 300
        ):
            raise TelnyxConfigurationError("Invalid Telnyx ingress configuration")
        # Snapshot only the validated ingress values, not mutable global settings
        # or administrative / outbound credentials. No channel-active check here.
        self._key = key
        self._phone_number = settings.telnyx_phone_number
        self._profile_id = settings.telnyx_messaging_profile_id
        self._waba_id = settings.telnyx_waba_id
        self._organization_id = settings.telnyx_organization_id
        self._max_body_bytes = settings.telnyx_webhook_max_body_bytes
        self._tolerance_seconds = settings.telnyx_webhook_tolerance_seconds
        self._clock = clock

    def authenticate(self, webhook: ProviderWebhookRequest) -> bytes:
        """Return original authenticated, scoped bytes, never a canonical event.

        Repeated deliveries inside the signature window remain valid. Neither
        event occurrence time nor channel/send readiness participates in crypto.
        """
        if (
            webhook.method != "POST"
            or not isinstance(webhook.body, bytes)
            or not 0 < len(webhook.body) <= self._max_body_bytes
            or webhook.content_type.lower().split(";", 1)[0].strip() != "application/json"
        ):
            raise InvalidWebhookPayload("Invalid Telnyx webhook request")
        # HTTP names are case insensitive. Reject ambiguous authentication headers
        # instead of choosing one. The future HTTP route must preserve duplicates.
        headers: dict[str, str] = {}
        for name, value in webhook.headers.items():
            normalized = name.lower()
            if normalized in {"telnyx-timestamp", "telnyx-signature-ed25519"}:
                if normalized in headers:
                    raise InvalidWebhookSignature("Invalid Telnyx webhook signature")
                headers[normalized] = value
        timestamp = headers.get("telnyx-timestamp", "")
        signature = headers.get("telnyx-signature-ed25519", "")
        try:
            if not re.fullmatch(r"[0-9]{1,12}", timestamp):
                raise ValueError("Invalid timestamp")
            now = self._clock()
            if not math.isfinite(now) or abs(now - int(timestamp)) > self._tolerance_seconds:
                raise ValueError("Invalid timestamp")
            self._key.verify(
                timestamp.encode("ascii") + b"|" + webhook.body, _decode_base64(signature, 64)
            )
        except (CryptoError, ValueError, TypeError, OverflowError, binascii.Error):
            raise InvalidWebhookSignature("Invalid Telnyx webhook signature") from None
        self._require_scope(webhook.body)
        return webhook.body

    def _require_scope(self, body: bytes) -> None:
        # Minimal envelope inspection AFTER crypto, solely to authorize scope.
        # Never inspect message content, origin, status or lifecycle transitions.
        try:
            envelope = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise InvalidWebhookPayload("Invalid Telnyx webhook envelope") from None
        data = envelope.get("data") if isinstance(envelope, dict) else None
        payload = data.get("payload") if isinstance(data, dict) else None
        if not isinstance(payload, dict) or data.get("record_type") != "event":
            raise InvalidWebhookPayload("Invalid Telnyx webhook envelope")

        # Optional scope identifiers, when supplied, must never contradict config.
        for name, expected in (
            ("messaging_profile_id", self._profile_id),
            ("organization_id", self._organization_id),
            ("waba_id", self._waba_id),
        ):
            if name in payload and payload[name] != expected:
                raise InvalidWebhookPayload("Invalid Telnyx webhook scope")

        event_type = data.get("event_type")
        if event_type == "whatsapp.account.update":
            valid = (
                payload.get("record_type") == "whatsapp_account"
                and payload.get("waba_id") == self._waba_id
            )
        elif event_type in (
            "message.received",
            "message.echo",
            "message.sent",
            "message.finalized",
            "message.read",
        ):
            inbound = event_type == "message.received"
            sender = payload.get("from")
            channel = (
                payload.get("to")
                if inbound
                else (sender.get("phone_number") if isinstance(sender, dict) else None)
            )
            valid = (
                payload.get("record_type") == "message"
                and payload.get("type") == "WHATSAPP"
                and payload.get("direction") == ("inbound" if inbound else "outbound")
                and payload.get("messaging_profile_id") == self._profile_id
                and payload.get("organization_id") == self._organization_id
                and channel == self._phone_number
            )
        else:
            # Unknown contracts have no verified scope rule yet. Never silently ACK.
            valid = False
        if not valid:
            raise InvalidWebhookPayload("Invalid Telnyx webhook scope")
