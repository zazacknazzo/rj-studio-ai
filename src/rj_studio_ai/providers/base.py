from abc import ABC, abstractmethod
from dataclasses import dataclass

from rj_studio_ai.domain import AIReply, InboundMessage


@dataclass(frozen=True, slots=True)
class ProviderWebhookRequest:
    method: str
    url: str
    headers: dict[str, str]
    query_string: bytes
    content_type: str
    body: bytes


@dataclass(frozen=True, slots=True)
class ProviderWebhookResponse:
    body: str
    media_type: str
    status_code: int = 200


class InvalidWebhookPayload(ValueError):
    """Raised when a provider callback is missing required Message data."""


class InvalidWebhookSignature(ValueError):
    """Raised when a provider callback cannot be authenticated."""


class WhatsAppProvider(ABC):
    @abstractmethod
    def receive(self, webhook: ProviderWebhookRequest) -> InboundMessage:
        """Authenticate and translate one provider callback."""

    @abstractmethod
    def reply(self, reply: AIReply) -> ProviderWebhookResponse:
        """Translate a canonical AI Reply into the provider response."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether the provider has its minimum local configuration."""
