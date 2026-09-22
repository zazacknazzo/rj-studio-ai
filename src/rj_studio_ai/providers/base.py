from abc import ABC, abstractmethod
from dataclasses import dataclass

from rj_studio_ai.domain import AIReply, OutboundMessage, ProviderWebhookEventBatch


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


class OutboundRetryableError(RuntimeError):
    """The provider proved non-acceptance and a later attempt may be safe."""


class OutboundPermanentError(RuntimeError):
    """The provider definitively rejected the outbound Message."""


class OutboundOutcomeUnknown(RuntimeError):
    """The provider may have accepted the outbound Message."""


@dataclass(frozen=True, slots=True)
class ProviderAcceptance:
    provider_message_id: str


class InboundWebhookAdapter(ABC):
    @abstractmethod
    def receive(self, webhook: ProviderWebhookRequest) -> ProviderWebhookEventBatch:
        """Authenticate and translate one provider callback into canonical events."""

    @abstractmethod
    def acknowledge(self) -> ProviderWebhookResponse:
        """Build an acknowledgement containing no customer-facing AI Reply."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether the provider has its minimum local configuration."""


class LegacyWebhookReplyRenderer(ABC):
    @abstractmethod
    def render_legacy_reply(self, reply: AIReply) -> ProviderWebhookResponse:
        """Render the current synchronous reply path during migration."""


class WhatsAppProvider(InboundWebhookAdapter, LegacyWebhookReplyRenderer):
    """Temporary composite used by the synchronous runtime through Migration 04."""


class OutboundMessageSender(ABC):
    @abstractmethod
    def send(
        self,
        message: OutboundMessage,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        """Submit one canonical outbound Message or raise a provider-neutral error."""
