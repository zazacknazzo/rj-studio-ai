from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class InboundMessage:
    provider: str
    provider_message_id: str
    customer_address: str
    recipient_address: str
    body: str


@dataclass(frozen=True, slots=True)
class InboundMessageReceived(InboundMessage):
    """Canonical provider event for one received Customer Message."""


class DeliveryStatus(StrEnum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DeliveryStatusReceived:
    """Canonical provider event for one outbound delivery status."""

    provider: str
    provider_message_id: str
    status: DeliveryStatus
    safe_error_code: str | None = None


ProviderWebhookEvent: TypeAlias = InboundMessageReceived | DeliveryStatusReceived


@dataclass(frozen=True, slots=True)
class ProviderWebhookEventBatch:
    """Canonical events authenticated and decoded from one provider callback."""

    events: tuple[ProviderWebhookEvent, ...]


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """Provider-neutral customer-directed content awaiting submission."""

    sender_address: str
    recipient_address: str
    body: str


@dataclass(frozen=True, slots=True)
class MessageRecord:
    direction: str
    body: str


@dataclass(frozen=True, slots=True)
class AIReply:
    body: str
