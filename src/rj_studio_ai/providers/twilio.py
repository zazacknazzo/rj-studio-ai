from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from rj_studio_ai.domain import InboundMessage, WebhookInput, WebhookResponse
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    WhatsAppProvider,
)


class TwilioProvider(WhatsAppProvider):
    name = "twilio"

    def __init__(self, *, auth_token: str, validate_signature: bool) -> None:
        self._auth_token = auth_token
        self._validate_signature = validate_signature

    def receive(self, webhook: WebhookInput) -> InboundMessage:
        if self._validate_signature and not self._has_valid_signature(webhook):
            raise InvalidWebhookSignature("Invalid Twilio webhook signature")

        required_fields = ("MessageSid", "From", "To", "Body")
        missing = [field for field in required_fields if not webhook.form.get(field)]
        if missing:
            raise InvalidWebhookPayload(f"Missing required Twilio fields: {', '.join(missing)}")

        return InboundMessage(
            provider=self.name,
            provider_message_id=webhook.form["MessageSid"],
            customer_address=webhook.form["From"],
            recipient_address=webhook.form["To"],
            body=webhook.form["Body"],
        )

    def reply(self, message: InboundMessage, body: str) -> WebhookResponse:
        response = MessagingResponse()
        response.message(body)
        return WebhookResponse(body=str(response), media_type="application/xml")

    def acknowledge(self) -> WebhookResponse:
        return WebhookResponse(
            body=str(MessagingResponse()),
            media_type="application/xml",
        )

    def _has_valid_signature(self, webhook: WebhookInput) -> bool:
        signature = webhook.headers.get("x-twilio-signature", "")
        if not self._auth_token or not signature:
            return False
        return RequestValidator(self._auth_token).validate(
            webhook.url,
            webhook.form,
            signature,
        )
