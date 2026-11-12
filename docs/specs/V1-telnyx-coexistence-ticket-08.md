# Telnyx Coexistence V1 — Ticket 08

Status: authorized by the user's Ticket 08 instruction on 2026-11-12, implementing
that approved scope. Baseline 5f0592d268916c6eee042de2fd73ee171030e47b, Tickets 01–07.
Issue #11/CX-31 is the correlation gate. Tickets 09–13 remain unauthorized.

## Verified wire contract

Reuse TelnyxWebhookAuthenticator before parsing. The official outbound schema has
an array `payload.to`, unlike the scalar `to` on Ticket 07 inbound/echo envelopes.
Require exactly one recipient with E.164 phone_number and a recognized status;
reject cc recipients, human origin, wrong number/profile/organization, malformed
identity and contradictory event/status combinations. data.id is the event;
payload.id is the Telnyx Message. Never join by foreign_id/Meta alias or body text.

| Event | Recipient status | Canonical evidence |
| --- | --- | --- |
| message.sent | sent | sent |
| message.sent / message.finalized | queued, sending | unknown observation only |
| message.finalized | sent, delivered, read | corresponding status |
| message.finalized | sending_failed, delivery_failed, failed | failed, fixed safe reason |
| message.finalized | delivery_unconfirmed, expired | unknown observation only |
| message.read | read | read |

Only explicit failure statuses map to failed; errors[].code/title/detail are
untrusted and discarded. `failed` is documented in the WhatsApp coexistence guide,
though absent from the generic enum. `expired` has no sufficiently precise
failure/retry semantics, so it is retained as unknown. Queued/sending do not prove
Provider Acceptance locally. No fallback from event type or accepted to delivered.

## Durable correlation

A separate scoped status ledger replaces pending_delivery_statuses **for Telnyx
only**. Preserve that legacy table and Meta/Twilio behavior/data. Every receipt
retains provider, event/Message IDs, channel, recipient, account/profile, occurrence,
verified source event/status and first receipt time; no content, raw payload or
external error strings. Events are globally unique within provider; conflicting
replays fail closed. All events for a provider Message must have identical scope.
Inbound/human identities cannot double as AI status; aliases are never lookup keys.

Before local Provider Acceptance, retain receipts without creating Message,
Conversation, generation, attempt, or delivery. At acceptance, validate the outbox
provider/channel/recipient/Message and link receipts in the same BEGIN IMMEDIATE
transaction as attempt finalization. Mismatch rolls back acceptance. Never consume
unscoped legacy pending rows for Telnyx. After acceptance, perform the same checks
before any status change. Replay/restart before or after reconciliation is safe.
No callback claims work, resends, or changes unknown/cancelled into sendable work.

## Precedence and contradictions

Success evidence is monotonic sent < delivered < read, independent of arrival/time.
A failure without confirmed delivered/read yields failed. Failure plus delivered
or read preserves the highest confirmed success and sets a durable status_conflict
flag with a fixed safe reason. This aggregate is independent of callback order.
The full minimal ledger retains both sides. A conflict blocks subsequent ordered
processing/submission and appears in redacted blocked-delivery inspection and
unresolved_delivery. It cannot be cleared by status replay or administrative resume.
Manual conflict resolution is a later, separately approved recovery policy.
Unknown observations never authorize/retry; cancelled and unknown local outcomes
remain untouched. Legacy failed precedence is unchanged for Meta/Twilio.

## Validation and boundaries

Exercise signed official-shape payloads, bad signatures/scope, every supported
status, replay/conflicts/order, acceptance races, restart, wrong channel/customer,
shared aliases, SQLite statement/commit rollback, lost ACK, human echo, unknown,
terminal contradictions, privacy, migrations, and Tickets 01–07 regression.
Run full pytest, Ruff check/format, compileall, pip check, diff check, secret audit
and independent Standards/Spec reviews. Publish only the Ticket 08 branch normally.
No sender, lifecycle, service window, public route, readiness, real account,
Baileys, main, or frozen intelligence changes.

CX-01 retention covers the new private ledger too. CX-24/29/30 HTTP gates stay open;
offline ACK follows commit, not a production 2-second latency guarantee.

Sources verified 2026-11-12:
- https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks
- https://developers.telnyx.com/docs/messaging/whatsapp/coexistence
- https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json
  (`MessagingOutboundMessage`, `MessagingOutboundMessagePayload`).
