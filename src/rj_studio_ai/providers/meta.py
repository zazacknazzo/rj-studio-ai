import hashlib
import hmac
import json
import re
from collections.abc import Callable
from typing import Any, Protocol

import requests
from requests import RequestException

from rj_studio_ai.domain import (
    AIReply,
    DeliveryStatus,
    DeliveryStatusReceived,
    InboundMessageReceived,
    OutboundMessage,
    ProviderWebhookEvent,
    ProviderWebhookEventBatch,
)
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
    ProviderWebhookRequest,
    ProviderWebhookResponse,
    WhatsAppProvider,
)

_WAMID = re.compile(r"^wamid\.[^\s]+$")
_PHONE_NUMBER_ID = re.compile(r"^[0-9]+$")
_API_VERSION = re.compile(r"^v[0-9]+\.[0-9]+$")


class _HTTPResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


class MetaProvider(WhatsAppProvider):
    """Authenticate and normalize Meta WhatsApp Cloud API webhooks."""

    name = "meta"

    def __init__(self, *, verify_token: str, app_secret: str) -> None:
        self._verify_token = verify_token
        self._app_secret = app_secret

    def is_configured(self) -> bool:
        return bool(self._verify_token.strip() and self._app_secret.strip())

    def verify_subscription(
        self,
        *,
        mode: str | None,
        verify_token: str | None,
        challenge: str | None,
    ) -> ProviderWebhookResponse:
        if (
            not self.is_configured()
            or mode != "subscribe"
            or verify_token is None
            or not hmac.compare_digest(verify_token, self._verify_token)
            or challenge is None
            or not challenge
        ):
            raise InvalidWebhookSignature("Invalid Meta webhook verification")
        return ProviderWebhookResponse(body=challenge, media_type="text/plain")

    def receive(self, webhook: ProviderWebhookRequest) -> ProviderWebhookEventBatch:
        self._require_valid_signature(webhook)
        if webhook.content_type.lower().split(";", 1)[0].strip() != "application/json":
            raise InvalidWebhookPayload("Unsupported Meta webhook content type")
        try:
            payload = json.loads(webhook.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidWebhookPayload("Malformed Meta webhook JSON") from error
        if not isinstance(payload, dict):
            raise InvalidWebhookPayload("Invalid Meta webhook envelope")
        if payload.get("object") != "whatsapp_business_account":
            raise InvalidWebhookPayload("Invalid Meta webhook object")
        entries = payload.get("entry")
        if not isinstance(entries, list):
            raise InvalidWebhookPayload("Invalid Meta webhook entries")

        events: list[ProviderWebhookEvent] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise InvalidWebhookPayload("Invalid Meta webhook entry")
            changes = entry.get("changes")
            if not isinstance(changes, list):
                raise InvalidWebhookPayload("Invalid Meta webhook changes")
            for change in changes:
                if not isinstance(change, dict):
                    raise InvalidWebhookPayload("Invalid Meta webhook change")
                if change.get("field") != "messages":
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    raise InvalidWebhookPayload("Invalid Meta messages value")
                if value.get("messaging_product") != "whatsapp":
                    raise InvalidWebhookPayload("Invalid Meta messaging product")
                events.extend(self._events_from_value(value))
        return ProviderWebhookEventBatch(events=tuple(events))

    def acknowledge(self) -> ProviderWebhookResponse:
        return ProviderWebhookResponse(body="", media_type="text/plain")

    def render_legacy_reply(self, reply: AIReply) -> ProviderWebhookResponse:
        del reply
        raise RuntimeError("Meta does not support legacy webhook replies")

    def _require_valid_signature(self, webhook: ProviderWebhookRequest) -> None:
        supplied = webhook.headers.get("x-hub-signature-256", "")
        if not self._app_secret or not supplied.startswith("sha256="):
            raise InvalidWebhookSignature("Invalid Meta webhook signature")
        expected = hmac.new(
            self._app_secret.encode("utf-8"),
            webhook.body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied[7:], expected):
            raise InvalidWebhookSignature("Invalid Meta webhook signature")

    def _events_from_value(self, value: dict[str, object]) -> list[ProviderWebhookEvent]:
        metadata = value.get("metadata")
        phone_number_id = metadata.get("phone_number_id") if isinstance(metadata, dict) else None
        messages = value.get("messages", [])
        statuses = value.get("statuses", [])
        if not isinstance(messages, list) or not isinstance(statuses, list):
            raise InvalidWebhookPayload("Invalid Meta messages or statuses")

        events: list[ProviderWebhookEvent] = []
        for message in messages:
            if not isinstance(message, dict):
                raise InvalidWebhookPayload("Invalid Meta Message")
            if message.get("type") != "text":
                continue
            text = message.get("text")
            body = text.get("body") if isinstance(text, dict) else None
            provider_message_id = message.get("id")
            customer_address = message.get("from")
            if not all(
                isinstance(value, str) and value.strip()
                for value in (phone_number_id, provider_message_id, customer_address, body)
            ):
                raise InvalidWebhookPayload("Invalid Meta text Message")
            if not _WAMID.fullmatch(str(provider_message_id)):
                raise InvalidWebhookPayload("Invalid Meta inbound Message ID")
            events.append(
                InboundMessageReceived(
                    provider=self.name,
                    provider_message_id=str(provider_message_id),
                    customer_address=str(customer_address),
                    recipient_address=str(phone_number_id),
                    body=str(body),
                )
            )

        status_mapping = {
            "sent": DeliveryStatus.SENT,
            "delivered": DeliveryStatus.DELIVERED,
            "read": DeliveryStatus.READ,
            "failed": DeliveryStatus.FAILED,
        }
        for status in statuses:
            if not isinstance(status, dict):
                raise InvalidWebhookPayload("Invalid Meta delivery status")
            canonical = status_mapping.get(status.get("status"))
            if canonical is None:
                continue
            provider_message_id = status.get("id")
            if not isinstance(provider_message_id, str) or not _WAMID.fullmatch(
                provider_message_id
            ):
                raise InvalidWebhookPayload("Invalid Meta status Message ID")
            events.append(
                DeliveryStatusReceived(
                    provider=self.name,
                    provider_message_id=provider_message_id,
                    status=canonical,
                    safe_error_code=(
                        "provider_failed" if canonical is DeliveryStatus.FAILED else None
                    ),
                )
            )
        return events


class MetaOutboundMessageSender(OutboundMessageSender):
    """Submit eligible canonical text through the Meta Graph API."""

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        api_version: str,
        free_form_is_eligible: Callable[[OutboundMessage], bool],
        post: Callable[..., _HTTPResponse] | None = None,
    ) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._api_version = api_version
        self._free_form_is_eligible = free_form_is_eligible
        self._post = post or requests.post

    def is_configured(self) -> bool:
        return bool(
            self._access_token.strip()
            and _PHONE_NUMBER_ID.fullmatch(self._phone_number_id)
            and _API_VERSION.fullmatch(self._api_version)
        )

    def send(
        self,
        message: OutboundMessage,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        if timeout_seconds <= 0:
            raise ValueError("Outbound timeout must be positive")
        if not self.is_configured():
            raise OutboundPermanentError("meta_not_configured")
        if (
            message.sender_address != self._phone_number_id
            or not message.recipient_address.strip()
            or not message.body.strip()
        ):
            raise OutboundPermanentError("meta_invalid_message")
        if not self._free_form_is_eligible(message):
            raise OutboundPermanentError("meta_free_form_not_eligible")

        try:
            response = self._post(
                (
                    f"https://graph.facebook.com/{self._api_version}/"
                    f"{self._phone_number_id}/messages"
                ),
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": message.recipient_address,
                    "type": "text",
                    "text": {"preview_url": False, "body": message.body},
                },
                timeout=timeout_seconds,
            )
        except RequestException as error:
            raise OutboundOutcomeUnknown("meta_outcome_unknown") from error
        except OSError as error:
            raise OutboundOutcomeUnknown("meta_outcome_unknown") from error

        try:
            payload = response.json()
        except (ValueError, TypeError) as error:
            raise OutboundOutcomeUnknown("meta_response_ambiguous") from error
        if 200 <= response.status_code < 300:
            provider_message_id = self._accepted_message_id(payload)
            if provider_message_id is None:
                raise OutboundOutcomeUnknown("meta_response_ambiguous")
            return ProviderAcceptance(provider_message_id=provider_message_id)

        error = payload.get("error") if isinstance(payload, dict) else None
        is_transient = error.get("is_transient") if isinstance(error, dict) else None
        if response.status_code == 429 or is_transient is True:
            raise OutboundRetryableError("meta_rate_limited")
        if is_transient is False or response.status_code in {401, 403}:
            raise OutboundPermanentError("meta_request_rejected")
        raise OutboundOutcomeUnknown("meta_outcome_unknown")

    @staticmethod
    def _accepted_message_id(payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None
        messages = payload.get("messages")
        if not isinstance(messages, list) or len(messages) != 1:
            return None
        first = messages[0]
        if not isinstance(first, dict):
            return None
        identifier: Any = first.get("id")
        if not isinstance(identifier, str) or not _WAMID.fullmatch(identifier):
            return None
        return identifier
