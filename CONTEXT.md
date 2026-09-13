# RJ Studio AI

RJ Studio AI handles WhatsApp conversations between the salon and its customers while keeping channel-specific behavior replaceable.

## Language

**Conversation**:
The continuing WhatsApp exchange between RJ Studio and one customer.
_Avoid_: Chat, thread, session

**Message**:
One inbound or outbound item within a Conversation.
_Avoid_: Event, payload

**Customer**:
The person contacting RJ Studio through WhatsApp.
_Avoid_: User, contact, lead

**Automatic Reply**:
The fixed response sent after an inbound Message in V0.
_Avoid_: AI response, bot response

**WhatsApp Provider**:
The external channel service that receives and sends WhatsApp Messages for RJ Studio.
_Avoid_: Gateway, vendor
