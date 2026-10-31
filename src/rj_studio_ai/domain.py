from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias


class EventOrigin(StrEnum):
    CUSTOMER = "customer"
    HUMAN_OPERATOR = "human_operator"
    PROVIDER = "provider"


def _require_identifiers(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Canonical event requires nonempty identifiers")


@dataclass(frozen=True, slots=True)
class MessageReference:
    """Opaque Message identity in an explicit namespace, never an event identifier."""

    namespace: str
    message_id: str

    def __post_init__(self) -> None:
        _require_identifiers(self.namespace, self.message_id)


@dataclass(frozen=True, slots=True)
class ProviderEventMetadata:
    """Adapter-supplied provenance; neither authentication nor a concurrency token."""

    event_id: str
    origin: EventOrigin
    occurred_at: datetime
    message_aliases: tuple[MessageReference, ...] = ()
    message_occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_identifiers(self.event_id)
        if not isinstance(self.origin, EventOrigin):
            raise ValueError("Canonical event requires an explicit origin")
        timestamps = (self.occurred_at,)
        if self.message_occurred_at is not None:
            timestamps += (self.message_occurred_at,)
        for timestamp in timestamps:
            if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
                raise ValueError("Canonical event requires timezone-aware timestamps")
        if not isinstance(self.message_aliases, tuple) or any(
            not isinstance(alias, MessageReference) for alias in self.message_aliases
        ):
            raise ValueError("Canonical event requires immutable Message references")


def _require_origin(metadata: ProviderEventMetadata, *origins: EventOrigin) -> None:
    if not isinstance(metadata, ProviderEventMetadata) or metadata.origin not in origins:
        raise ValueError("Canonical event origin does not match its type")


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

    metadata: ProviderEventMetadata | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        # Missing provenance preserves the existing Meta/Twilio contract.
        if self.metadata is not None:
            _require_origin(self.metadata, EventOrigin.CUSTOMER)


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
    metadata: ProviderEventMetadata | None = field(default=None, kw_only=True)
    channel_id: str | None = field(default=None, kw_only=True)
    customer_address: str | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if self.metadata is not None:
            _require_origin(self.metadata, EventOrigin.PROVIDER)
        for identifier in (self.channel_id, self.customer_address):
            if identifier is not None:
                _require_identifiers(identifier)


@dataclass(frozen=True, slots=True)
class HumanMessageObserved:
    """Outbound human activity without Customer input or AI Reply content."""

    provider: str
    provider_message_id: str
    channel_id: str
    customer_address: str
    metadata: ProviderEventMetadata

    def __post_init__(self) -> None:
        _require_identifiers(
            self.provider, self.provider_message_id, self.channel_id, self.customer_address
        )
        _require_origin(self.metadata, EventOrigin.HUMAN_OPERATOR)


@dataclass(frozen=True, slots=True)
class MessageEdited:
    """Observation of an edit; original identity is not a new Customer Message."""

    provider: str
    provider_message_id: str
    channel_id: str
    customer_address: str
    original_message: MessageReference
    metadata: ProviderEventMetadata

    def __post_init__(self) -> None:
        _require_message_change(self)


@dataclass(frozen=True, slots=True)
class MessageRevoked:
    """Observation of a revocation, with no text eligible for AI generation."""

    provider: str
    provider_message_id: str
    channel_id: str
    customer_address: str
    original_message: MessageReference
    metadata: ProviderEventMetadata

    def __post_init__(self) -> None:
        _require_message_change(self)


def _require_message_change(event: MessageEdited | MessageRevoked) -> None:
    _require_identifiers(
        event.provider, event.provider_message_id, event.channel_id, event.customer_address
    )
    if not isinstance(event.original_message, MessageReference):
        raise ValueError("Message change requires its original Message reference")
    _require_origin(event.metadata, EventOrigin.CUSTOMER, EventOrigin.HUMAN_OPERATOR)


class ChannelScope(StrEnum):
    ACCOUNT = "account"
    CHANNEL = "channel"


class ChannelAvailability(StrEnum):
    BLOCKED = "blocked"
    VERIFICATION_REQUIRED = "verification_required"


class ChannelLifecycleReason(StrEnum):
    OFFBOARDED = "offboarded"
    DISCONNECTED = "disconnected"
    RECONNECTED = "reconnected"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True, slots=True)
class ChannelAvailabilityChanged:
    """Operational lifecycle observation, never proof that sending is enabled."""

    provider: str
    scope: ChannelScope
    scope_id: str
    availability: ChannelAvailability
    reason: ChannelLifecycleReason
    metadata: ProviderEventMetadata

    def __post_init__(self) -> None:
        _require_identifiers(self.provider, self.scope_id)
        if (
            not isinstance(self.scope, ChannelScope)
            or not isinstance(self.availability, ChannelAvailability)
            or not isinstance(self.reason, ChannelLifecycleReason)
        ):
            raise ValueError("Invalid canonical channel lifecycle")
        _require_origin(self.metadata, EventOrigin.PROVIDER)
        if self.metadata.message_aliases or self.metadata.message_occurred_at is not None:
            raise ValueError("Channel lifecycle cannot identify a Message")


ProviderWebhookEvent: TypeAlias = (
    InboundMessageReceived
    | DeliveryStatusReceived
    | HumanMessageObserved
    | MessageEdited
    | MessageRevoked
    | ChannelAvailabilityChanged
)


class ProviderEventKind(StrEnum):
    CUSTOMER_MESSAGE = "customer_message"
    HUMAN_ACTIVITY = "human_activity"
    DELIVERY_STATUS = "delivery_status"
    CHANNEL_LIFECYCLE = "channel_lifecycle"
    MESSAGE_EDIT = "message_edit"
    MESSAGE_REVOCATION = "message_revocation"


def classify_provider_event(event: object) -> ProviderEventKind:
    """Classify canonical values only; never guess from wire payloads or body text."""
    kinds = {
        InboundMessage: ProviderEventKind.CUSTOMER_MESSAGE,  # Historical internal input.
        InboundMessageReceived: ProviderEventKind.CUSTOMER_MESSAGE,
        HumanMessageObserved: ProviderEventKind.HUMAN_ACTIVITY,
        DeliveryStatusReceived: ProviderEventKind.DELIVERY_STATUS,
        ChannelAvailabilityChanged: ProviderEventKind.CHANNEL_LIFECYCLE,
        MessageEdited: ProviderEventKind.MESSAGE_EDIT,
        MessageRevoked: ProviderEventKind.MESSAGE_REVOCATION,
    }
    kind = kinds.get(type(event))
    if kind is None:
        raise ValueError("Unsupported canonical provider event")
    if isinstance(event, InboundMessage):
        _require_identifiers(
            event.provider,
            event.provider_message_id,
            event.customer_address,
            event.recipient_address,
            event.body,
        )
    elif isinstance(event, DeliveryStatusReceived):
        _require_identifiers(event.provider, event.provider_message_id)
        if not isinstance(event.status, DeliveryStatus):
            raise ValueError("Invalid canonical delivery status")
    return kind


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
    submission_key: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True, slots=True)
class MessageRecord:
    direction: str
    body: str


@dataclass(frozen=True, slots=True)
class AIReply:
    body: str
