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
class WebhookInput:
    url: str
    headers: dict[str, str]
    form: dict[str, str]


@dataclass(frozen=True, slots=True)
class WebhookResponse:
    body: str
    media_type: str
    status_code: int = 200
