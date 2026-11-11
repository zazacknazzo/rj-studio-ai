# Ticket 07 — authenticated Message parsing and durable ingress

Status: authorized by the user's explicit Ticket 07 request, 2026-11-11.
Base: `5b8f561250499ae2463688caf37d3876e7fa60a4`. Tickets 08–13 remain unauthorized.
Read the complete risk register [issue #11](https://github.com/zazacknazzo/rj-studio-ai/issues/11).

## Contract

Re-use Ticket 06 authentication on original bytes before parsing. Require scoped
WHATSAPP envelopes with direction, event ID, logical Message ID, event occurrence,
Customer and fixed business number. Optional body.id must match payload.id.
Explicit phone evidence must agree; hidden numbers use body.from_user_id as an
opaque, namespaced Customer address (`bsuid:`). Never merge phone and BSUID identities.

- message.received + body.type=text: InboundMessageReceived from body.text.body only.
- message.echo: require outbound and origin=whatsapp_business_app; HumanMessageObserved
  regardless of content (text/media/empty/unknown), without any text in the event.
- message.received + edit/revoke: MessageEdited/MessageRevoked. Preserve the opaque
  original_message_id in namespace `telnyx_original_opaque`; do not guess UUID versus
  wamid, mutate history, cancel the original reply or generate another reply.
- Other inbound formats, WABA whatsapp.messages, unknown events, status and lifecycle
  fail closed without ACK. No unsupported receipt is claimed. Status/lifecycle await
  Tickets 08/09 and the external route awaits Ticket 12.

Event identity is data.id; logical Message identity is payload.id; body.foreign_id
is an optional alias in namespace `meta`. Aliases never identify a Conversation or
collapse logical Messages. Event time is data.occurred_at. Source Message time is
only body.timestamp (ASCII Unix-seconds string), valid when source <= event <= local
receipt. Invalid/missing/contradictory source becomes unavailable; never substitute
signature/receipt/envelope time. Existing Ticket 05 policy permanently suppresses
old/unproven inbound after resume; only source strictly newer than cutoff is eligible.
No positive skew allowance at the resume gate. Plausibly wrong remote times remain
an operational clock/provenance risk. Envelope times must be timezone-aware RFC3339.

## Persistence and ACK

Use record_webhook_events and the existing operational journal/effects. Add a side
receipt table for inbound metadata, without rebuilding Messages or the operational
journal. Hold minimal identities/aliases/source and first receipt times across raw
content purge; no content/hash/raw payload copy. Same event with conflicting evidence
fails; repeated logical inbound cannot generate twice, including a new envelope after
purge/restart. Conflicting Message scope/content (while content retained) fails.
Operational duplicate envelopes remain observations, while human_pause_effects applies
one pause per exact logical identity. An unseen delayed human Message repauses after
resume; shared aliases do not suppress a distinct Message. Unresolvable human effects
must not ACK. Reject channel ambiguity before effects or generation.

The dormant receive_telnyx_messages interface authenticates/parses every request,
then commits one SQLite transaction before returning an empty 204. Its tuple is a
local test/composition batch, not a claimed Telnyx wire format (one envelope per request).
No LLM/sender dependency exists. Tests use real SQLite and the existing fake sender.
Deadline includes parsing, bounded lock acquisition, SQL progress, precommit check and
postcommit ACK check. SQLite failure or expiration cannot return success; commit that
finishes after the deadline may remain durable and is safely replayable. Filesystem
fsync cannot be preempted; this is no hard real-time latency claim.

## Verification and exclusions

Synthetic signed official-shape payloads test classification, malformed/type/identity
errors, authentication-first, E.164/opaque identity, distinct event/Message/Meta IDs,
ambiguous original references, replay/out-of-order/restart, temporal resume boundaries,
delayed echoes, SQLite statement/commit failures, mixed rollback, lost ACK, contention,
concurrent echo versus generation and send authorization, privacy and full Meta/Twilio
regressions. Run full pytest, Ruff check/format, compilation, diff/secret audit and
independent Standards/Spec reviews before normal push of Ticket 07 only.

No factory/configuration/runtime route, status/lifecycle, sender/window/idempotency-key,
Baileys, main or intelligence changes. Raw header duplication and streaming enforcement
remain CX-24/Ticket 12. Retention remains CX-01; echo best-effort CX-02; clocks CX-05;
external submission race CX-06. No real-provider readiness is asserted.

Sources verified 2026-11-11:
[Coexistence](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks),
[official OpenAPI](https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json)
(MessagingInboundMessagePayload, WhatsappMessageEchoPayload).
