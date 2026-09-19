from urllib.parse import parse_qsl

from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from rj_studio_ai.domain import AIReply, InboundMessage
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    ProviderWebhookRequest,
    ProviderWebhookResponse,
    WhatsAppProvider,
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
    ) -> None:
        self._auth_token = auth_token
        self._validate_signature = validate_signature
        self._public_webhook_url = public_webhook_url

    def receive(self, webhook: ProviderWebhookRequest) -> InboundMessage:
        form = self._parse_form(webhook)
        if self._validate_signature and not self._has_valid_signature(webhook, form):
            raise InvalidWebhookSignature("Invalid Twilio webhook signature")

        required_fields = ("MessageSid", "From", "To", "Body")
        missing = [field for field in required_fields if not form.get(field)]
        if missing:
            raise InvalidWebhookPayload(f"Missing required Twilio fields: {', '.join(missing)}")

        return InboundMessage(
            provider=self.name,
            provider_message_id=form["MessageSid"],
            customer_address=form["From"],
            recipient_address=form["To"],
            body=form["Body"],
        )

    def reply(self, reply: AIReply) -> ProviderWebhookResponse:
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
    ) -> bool:
        signature = webhook.headers.get("x-twilio-signature", "")
        if not self._auth_token or not signature:
            return False
        public_url = self._public_webhook_url or webhook.url
        return RequestValidator(self._auth_token).validate(
            public_url,
            form,
            signature,
        )
