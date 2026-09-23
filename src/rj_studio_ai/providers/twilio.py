import re
from collections.abc import Callable
from typing import Protocol
from urllib.parse import parse_qsl, urlsplit

from requests import ConnectionError as RequestsConnectionError
from requests import Timeout as RequestsTimeout
from twilio.base.exceptions import TwilioException, TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.request_validator import RequestValidator
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from rj_studio_ai.domain import (
    AIReply,
    DeliveryStatus,
    DeliveryStatusReceived,
    InboundMessageReceived,
    OutboundMessage,
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

_TWILIO_MESSAGE_SID = re.compile(r"^(?:SM|MM)[0-9a-fA-F]{32}$")
_TWILIO_ACCOUNT_SID = re.compile(r"^AC[0-9a-fA-F]{32}$")
_TWILIO_API_KEY_SID = re.compile(r"^SK[0-9a-fA-F]{32}$")
_TWILIO_PERMANENT_MESSAGE_ERROR_CODES = frozenset(
    {
        20003,  # Authentication Error
        21211,  # Invalid 'To' Phone Number
        21212,  # Invalid 'From' Phone Number
        21606,  # 'From' is not a valid message-capable Twilio number
        21614,  # 'To' is not a valid mobile number
        63007,  # Channel sender is not configured for this account
    }
)


class _MessagesResource(Protocol):
    def create(self, **kwargs: str) -> object: ...


class _TwilioClient(Protocol):
    messages: _MessagesResource


class TwilioOutboundSender(OutboundMessageSender):
    """Submit canonical outbound content through Twilio's Message resource."""

    def __init__(
        self,
        *,
        account_sid: str,
        api_key_sid: str,
        api_key_secret: str,
        status_callback_url: str,
        client_factory: Callable[[float], _TwilioClient] | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._api_key_sid = api_key_sid
        self._api_key_secret = api_key_secret
        self._status_callback_url = status_callback_url
        self._client_factory = client_factory or self._build_client

    def is_configured(self) -> bool:
        callback = urlsplit(self._status_callback_url)
        return bool(
            _TWILIO_ACCOUNT_SID.fullmatch(self._account_sid)
            and _TWILIO_API_KEY_SID.fullmatch(self._api_key_sid)
            and self._api_key_secret.strip()
            and callback.scheme == "https"
            and callback.hostname
            and "_" not in callback.hostname
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
            raise OutboundPermanentError("twilio_not_configured")
        if (
            not message.sender_address.startswith("whatsapp:")
            or not message.recipient_address.startswith("whatsapp:")
            or not message.body.strip()
        ):
            raise OutboundPermanentError("twilio_invalid_message")
        try:
            created = self._client_factory(timeout_seconds).messages.create(
                from_=message.sender_address,
                to=message.recipient_address,
                body=message.body,
                status_callback=self._status_callback_url,
            )
        except TwilioRestException as error:
            if error.status == 429:
                raise OutboundRetryableError("twilio_rate_limited") from error
            if error.code in _TWILIO_PERMANENT_MESSAGE_ERROR_CODES:
                raise OutboundPermanentError("twilio_request_rejected") from error
            raise OutboundOutcomeUnknown("twilio_outcome_unknown") from error
        except (
            RequestsTimeout,
            RequestsConnectionError,
            TwilioException,
            OSError,
            ValueError,
            KeyError,
        ) as error:
            raise OutboundOutcomeUnknown("twilio_outcome_unknown") from error

        provider_message_id = getattr(created, "sid", None)
        if not isinstance(provider_message_id, str) or not _TWILIO_MESSAGE_SID.fullmatch(
            provider_message_id
        ):
            raise OutboundOutcomeUnknown("twilio_response_ambiguous")
        return ProviderAcceptance(provider_message_id=provider_message_id)

    def _build_client(self, timeout_seconds: float) -> _TwilioClient:
        return Client(
            self._api_key_sid,
            self._api_key_secret,
            account_sid=self._account_sid,
            http_client=TwilioHttpClient(timeout=timeout_seconds, max_retries=0),
        )


class _TwilioForm(dict[str, str]):
    def __init__(self, pairs: list[tuple[str, str]]) -> None:
        super().__init__(pairs)
        self._values: dict[str, list[str]] = {}
        for key, value in pairs:
            self._values.setdefault(key, []).append(value)

    def getall(self, key: str) -> list[str]:
        return self._values.get(key, [])


class TwilioProvider(WhatsAppProvider):
    name = "twilio"

    def __init__(
        self,
        *,
        auth_token: str,
        validate_signature: bool,
        public_webhook_url: str | None,
        public_status_callback_url: str | None = None,
    ) -> None:
        self._auth_token = auth_token
        self._validate_signature = validate_signature
        self._public_webhook_url = public_webhook_url
        self._public_status_callback_url = public_status_callback_url

    def receive(self, webhook: ProviderWebhookRequest) -> ProviderWebhookEventBatch:
        form = self._parse_form(webhook)
        is_status_callback = "MessageStatus" in form or bool(form.get("EventType"))
        public_url = (
            self._public_status_callback_url if is_status_callback else self._public_webhook_url
        )
        if self._validate_signature and not self._has_valid_signature(
            webhook,
            form,
            public_url=public_url,
        ):
            raise InvalidWebhookSignature("Invalid Twilio webhook signature")

        if is_status_callback:
            return self._status_events(form)

        required_fields = ("MessageSid", "From", "To", "Body")
        missing = [field for field in required_fields if not form.get(field)]
        if missing:
            raise InvalidWebhookPayload(f"Missing required Twilio fields: {', '.join(missing)}")

        return ProviderWebhookEventBatch(
            events=(
                InboundMessageReceived(
                    provider=self.name,
                    provider_message_id=form["MessageSid"],
                    customer_address=form["From"],
                    recipient_address=form["To"],
                    body=form["Body"],
                ),
            )
        )

    def acknowledge(self) -> ProviderWebhookResponse:
        return ProviderWebhookResponse(body=str(MessagingResponse()), media_type="application/xml")

    def render_legacy_reply(self, reply: AIReply) -> ProviderWebhookResponse:
        response = MessagingResponse()
        response.message(reply.body)
        return ProviderWebhookResponse(body=str(response), media_type="application/xml")

    def is_configured(self) -> bool:
        return not self._validate_signature or bool(self._auth_token and self._public_webhook_url)

    def _parse_form(self, webhook: ProviderWebhookRequest) -> _TwilioForm:
        if webhook.content_type.lower().split(";", 1)[0].strip() != (
            "application/x-www-form-urlencoded"
        ):
            raise InvalidWebhookPayload("Unsupported Twilio webhook content type")
        try:
            body = webhook.body.decode("utf-8")
            return _TwilioForm(
                parse_qsl(
                    body,
                    keep_blank_values=True,
                    encoding="utf-8",
                    errors="strict",
                )
            )
        except (UnicodeDecodeError, ValueError) as error:
            raise InvalidWebhookPayload("Malformed Twilio webhook form body") from error

    def _has_valid_signature(
        self,
        webhook: ProviderWebhookRequest,
        form: _TwilioForm,
        *,
        public_url: str | None,
    ) -> bool:
        signature = webhook.headers.get("x-twilio-signature", "")
        if not self._auth_token or not signature:
            return False
        return RequestValidator(self._auth_token).validate(
            public_url or webhook.url,
            form,
            signature,
        )

    def _status_events(self, form: _TwilioForm) -> ProviderWebhookEventBatch:
        provider_message_id = form.get("MessageSid", "")
        if not _TWILIO_MESSAGE_SID.fullmatch(provider_message_id):
            raise InvalidWebhookPayload("Invalid or missing Twilio MessageSid")

        status_value = form.get("MessageStatus", "").lower()
        if form.get("EventType", "").upper() == "READ":
            status_value = "read"
        status_mapping = {
            "sent": DeliveryStatus.SENT,
            "delivered": DeliveryStatus.DELIVERED,
            "read": DeliveryStatus.READ,
            "failed": DeliveryStatus.FAILED,
            "undelivered": DeliveryStatus.FAILED,
        }
        canonical_status = status_mapping.get(status_value)
        if canonical_status is None:
            return ProviderWebhookEventBatch(events=())
        safe_error_code = None
        if status_value == "failed":
            safe_error_code = "provider_failed"
        elif status_value == "undelivered":
            safe_error_code = "provider_undelivered"
        return ProviderWebhookEventBatch(
            events=(
                DeliveryStatusReceived(
                    provider=self.name,
                    provider_message_id=provider_message_id,
                    status=canonical_status,
                    safe_error_code=safe_error_code,
                ),
            )
        )
