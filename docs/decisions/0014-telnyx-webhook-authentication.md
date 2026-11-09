# Authenticate Telnyx ingress without granting runtime or send readiness

Status: accepted for explicitly authorized Ticket 06.

Implement the Telnyx authentication boundary as a dormant authenticator, not an
incomplete canonical adapter returning an empty successful batch. Otherwise a
valid signature could cause an ACK that loses an event before semantic parsing
and durable effects exist. No Telnyx runtime selection or route is enabled.

Authenticate Ed25519 against the trusted configured raw public key using the
original timestamp text, a pipe and original bytes, before JSON inspection. Pin
the cryptographic implementation; reject invalid/missing inputs without logging
values or exposing underlying parsing exceptions. Scope authorization is separate
from signature validity: check the configured channel/profile/organization or
WABA according to the documented envelope. No Message or lifecycle semantics are
implemented. Authentication success returns original bytes, not canonical events.

A bounded symmetric timestamp window limits replay exposure but does not provide
event deduplication. The same recently signed request remains valid repeatedly;
old business events with new signatures remain eligible for downstream dedupe.
Do not compare occurred_at to the signature window or invent an in-memory receipt.

Snapshot validated local ingress configuration and keep it independent of channel
availability, outbound credentials, administrative Bearer authorization and LLM
health. A blocked sender must not prevent future authenticated operational ingress.
Conversely, local ingress configuration proves neither channel eligibility nor
send readiness. The approved contracts, outbox and pause/resume stay unchanged.

Later composition must enforce raw stream limits and reject duplicate HTTP headers
before the existing request dictionary loses that evidence. It must parse and
persist supported events durably before ACK, including operational events while
sending is blocked. This ADR grants no authorization to implement those tickets.
