from abc import ABC, abstractmethod

from rj_studio_ai.domain import InboundMessage, WebhookInput, WebhookResponse


class InvalidWebhookPayload(ValueError):
    """Raised when a provider callback is missing required Message data."""


class InvalidWebhookSignature(ValueError):
    """Raised when a provider callback cannot be authenticated."""


class WhatsAppProvider(ABC):
    @abstractmethod
    def receive(self, webhook: WebhookInput) -> InboundMessage:
        """Authenticate and translate one provider callback."""

    @abstractmethod
    def reply(self, message: InboundMessage, body: str) -> WebhookResponse:
        """Deliver a reply and describe the provider acknowledgement."""

    @abstractmethod
    def acknowledge(self) -> WebhookResponse:
        """Acknowledge a callback without sending another Message."""
