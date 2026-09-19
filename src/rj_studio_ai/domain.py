from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InboundMessage:
    provider: str
    provider_message_id: str
    customer_address: str
    recipient_address: str
    body: str


@dataclass(frozen=True, slots=True)
class MessageRecord:
    direction: str
    body: str


@dataclass(frozen=True, slots=True)
class AIReply:
    body: str
