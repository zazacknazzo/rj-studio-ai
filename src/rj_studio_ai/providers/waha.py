"""WAHA WEBJS text channel. No intelligence or conversation memory lives here."""

import hashlib
import hmac
import json
import re
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from time import time
from urllib.parse import urlparse

import httpx

from rj_studio_ai.domain import (
    EventOrigin,
    InboundMessageReceived,
    MessageReference,
    OutboundMessage,
    ProviderEventMetadata,
    ProviderWebhookEventBatch,
)
from rj_studio_ai.providers.base import (
    InboundWebhookAdapter,
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    ProviderAcceptance,
    ProviderWebhookRequest,
    ProviderWebhookResponse,
)


def phone_chat(value: str) -> str:
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        raise ValueError("phone_requires_e164")
    return value[1:] + "@c.us"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class WahaObservation:
    batch: ProviderWebhookEventBatch
    participant: str | None = None
    disconnected: bool = False
    opt_out: bool = False


class WahaAdapter(InboundWebhookAdapter):
    def __init__(self, *, secret, secondary, participants, session="default", clock=time):
        self._secret = secret
        self.secondary = phone_chat(secondary)
        self.participants = frozenset(phone_chat(p) for p in participants)
        self.session = session
        self.clock = clock
        self.identity_aliases = {value: value for value in (*self.participants, self.secondary)}
        if (
            len(secret) < 32
            or not 1 <= len(self.participants) <= 2
            or self.secondary in self.participants
            or session != "default"
        ):
            raise ValueError("invalid_private_waha_scope")

    def bind_verified_identities(self, aliases):
        allowed = self.participants | {self.secondary}
        bound = {value: value for value in allowed}
        for alias, canonical in aliases.items():
            if (
                canonical not in allowed
                or not re.fullmatch(r"[0-9]{1,20}@(c\.us|lid)", alias)
                or (alias in bound and bound[alias] != canonical)
            ):
                raise ValueError("waha_identity_conflict")
            bound[alias] = canonical
        self.identity_aliases = bound

    def is_configured(self):
        return True

    def acknowledge(self):
        return ProviderWebhookResponse(body="", media_type="application/json", status_code=204)

    def receive(self, webhook):
        return self.observe(webhook).batch

    def observe(self, webhook: ProviderWebhookRequest) -> WahaObservation:
        signature = webhook.headers.get("x-webhook-hmac", "")
        if (
            webhook.headers.get("x-webhook-hmac-algorithm") != "sha512"
            or not re.fullmatch(r"[a-f0-9]{128}", signature)
            or not hmac.compare_digest(
                signature, hmac.new(self._secret.encode(), webhook.body, hashlib.sha512).hexdigest()
            )
        ):
            raise InvalidWebhookSignature("waha_authentication")
        try:
            raw = json.loads(webhook.body, object_pairs_hook=_unique_object)
            if not isinstance(raw, dict) or raw.get("session") != self.session:
                raise ValueError()
            if raw.get("engine") != "WEBJS":
                raise ValueError()
            timestamp = raw["timestamp"]
            if type(timestamp) is not int or abs(self.clock() - timestamp / 1000) > 300:
                raise ValueError()
            payload = raw["payload"]
            if not isinstance(payload, dict):
                raise ValueError()
            empty = ProviderWebhookEventBatch(())
            if raw.get("event") == "session.status":
                # A reconnect observation never grants authority or resumes automation.
                return WahaObservation(empty, disconnected=payload.get("status") != "WORKING")
            if raw.get("event") != "message":
                return WahaObservation(empty)
            if self.identity_aliases.get(raw.get("me", {}).get("id")) != self.secondary:
                raise ValueError()
            raw_sender = payload.get("from")
            sender = self.identity_aliases.get(raw_sender)
            if (
                payload.get("fromMe") is not False
                or sender not in self.participants
                or self.identity_aliases.get(payload.get("to")) != self.secondary
                or payload.get("participant")
                or payload.get("hasMedia") is not False
            ):
                return WahaObservation(empty)
            # WEBJS uses chat in _data.type. Its public body alone could be a media caption.
            data = payload.get("_data")
            if not isinstance(data, dict) or data.get("type") != "chat":
                return WahaObservation(empty)
            body = payload["body"]
            message_id = payload["id"]
            event_id = raw["id"]
            occurred = payload["timestamp"]
            if (
                not isinstance(body, str)
                or not body.strip()
                or len(body.encode()) > 4096
                or not isinstance(message_id, str)
                or not re.fullmatch(
                    r"false_" + re.escape(raw_sender) + r"_[A-Za-z0-9_-]{1,128}", message_id
                )
                or not isinstance(event_id, str)
                or not re.fullmatch(r"evt_[a-zA-Z0-9_-]{1,128}", event_id)
                or type(occurred) is not int
                or abs(self.clock() - occurred) > 300
            ):
                raise ValueError()
            message = InboundMessageReceived(
                provider="waha",
                provider_message_id=message_id.replace(
                    "false_" + raw_sender + "_", "false_" + sender + "_", 1
                ),
                customer_address=sender,
                recipient_address=self.secondary,
                body=body,
                metadata=ProviderEventMetadata(
                    event_id=event_id,
                    origin=EventOrigin.CUSTOMER,
                    occurred_at=datetime.fromtimestamp(timestamp / 1000, UTC),
                    message_occurred_at=datetime.fromtimestamp(occurred, UTC),
                    message_aliases=(MessageReference("waha-wire", message_id),),
                ),
            )
            return WahaObservation(
                ProviderWebhookEventBatch((message,)),
                participant=sender,
                opt_out=body.strip().casefold().rstrip(".! ")
                in {
                    "pare",
                    "parar",
                    "stop",
                    "sair",
                    "cancelar mensagens",
                    "não me envie mensagens",
                },
            )
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
            raise InvalidWebhookPayload("waha_invalid_envelope") from None


class WahaIdentityError(ValueError):
    """Sanitized read-only verification failure; never a submission outcome."""


class WahaAPI:
    """Private HTTP API; never logs response bodies, session credentials or QR."""

    def __init__(self, *, base_url, api_key, session="default", client=None):
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "waha"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or session != "default"
            or len(api_key) < 32
        ):
            raise ValueError("waha_requires_private_endpoint")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session
        self.client = client

    def _request(self, method, path, *, payload=None, content=None, timeout=5):
        with (
            httpx.Client(trust_env=False) if self.client is None else nullcontext(self.client) as c
        ):
            return c.request(
                method,
                self.base_url + path,
                json=payload,
                content=content,
                headers={
                    "X-Api-Key": self.api_key,
                    **({"Content-Type": "application/json"} if content is not None else {}),
                },
                timeout=timeout,
                follow_redirects=False,
            )

    def request(self, method, path, *, payload=None, content=None, timeout=5):
        try:
            return self._request(method, path, payload=payload, content=content, timeout=timeout)
        except httpx.HTTPError:
            raise OutboundOutcomeUnknown("waha_transport_unknown") from None

    def session_info(self):
        response = self.request("GET", f"/api/sessions/{self.session}")
        if response.status_code != 200:
            raise OutboundPermanentError("waha_session_unavailable")
        try:
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except ValueError:
            raise OutboundPermanentError("waha_session_invalid") from None

    def identities_for(self, phone):
        canonical = phone_chat(phone)
        try:
            response = self._request(
                "GET",
                f"/api/contacts/check-exists?phone={phone[1:]}&session={self.session}",
                timeout=20,
            )
        except httpx.TimeoutException:
            raise WahaIdentityError("waha_contact_timeout") from None
        except httpx.HTTPError:
            raise WahaIdentityError("waha_contact_transport_failed") from None
        if response.status_code != 200:
            raise WahaIdentityError("waha_contact_http_unexpected")
        try:
            data = response.json()
            if data.get("numberExists") is not True:
                raise ValueError()
            aliases = {canonical, data["chatId"]}
            if data.get("pn"):
                aliases.add(data["pn"])
            if not all(
                isinstance(a, str) and re.fullmatch(r"[0-9]{1,20}@(c\.us|lid)", a) for a in aliases
            ):
                raise ValueError()
            return aliases
        except (ValueError, TypeError, KeyError, AttributeError):
            raise WahaIdentityError("waha_contact_identity_unverified") from None


class WahaTextSender(OutboundMessageSender):
    """Transport seam. Runtime store must authorize first; never retries a POST."""

    def __init__(self, *, api, secondary, participants, authorize_http):
        self.api = api
        self.secondary = phone_chat(secondary)
        self.participants = frozenset(phone_chat(p) for p in participants)
        self.authorize_http = authorize_http

    def send(self, message: OutboundMessage, *, timeout_seconds: float) -> ProviderAcceptance:
        if (
            message.sender_address != self.secondary
            or message.recipient_address not in self.participants
            or not message.body.strip()
            or not message.submission_key
            or not self.authorize_http(message)
        ):
            raise OutboundPermanentError("waha_egress_not_authorized")
        info = self.api.session_info()
        if info.get("status") != "WORKING" or (info.get("me") or {}).get("id") != self.secondary:
            raise OutboundPermanentError("waha_session_not_bound")
        response = self.api.request(
            "POST",
            "/api/sendText",
            payload={
                "session": self.api.session,
                "chatId": message.recipient_address,
                "text": message.body,
                "linkPreview": False,
            },
            timeout=timeout_seconds,
        )
        # Even an HTTP error may follow submission; WAHA has no proven idempotent retry.
        if response.status_code not in {200, 201}:
            raise OutboundOutcomeUnknown("waha_submission_unknown")
        try:
            raw = response.json()
            message_id = raw["id"]
            if (
                raw.get("fromMe") is not True
                or raw.get("to") != message.recipient_address
                or not isinstance(message_id, str)
                or not message_id.startswith("true_" + message.recipient_address + "_")
            ):
                raise ValueError()
            return ProviderAcceptance(message_id)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise OutboundOutcomeUnknown("waha_acceptance_invalid") from None
