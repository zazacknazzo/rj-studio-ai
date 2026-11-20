# Telnyx Coexistence V1 — Ticket 10

Status: authorized offline by the user's request on 2026-11-20 and the
[orchestrator's approval](https://github.com/zazacknazzo/rj-studio-ai/issues/11#issuecomment-6962756307).
Exact baseline: `c2cc68c0c714d8f8c642f7759f3799a90b3feae4`.
Branch: `codex/telnyx-coexistence-10-eligibility`. This spec is committed before code.
Tickets 11–13, real sending, public routes, activation, commercial credentials,
campaigns, follow-ups, CRM, intelligence changes, main and Baileys are excluded.

## External contracts checked 2026-11-20

- [Meta service messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages):
  customer activity opens a 24-hour service window; free-form requires that window,
  outside it requires approved templates. V1 supports only legitimate inbound text
  evidence, not calls. Opt-in is a separate requirement.
- [WhatsApp policy](https://business.whatsapp.com/policy) and
  [Meta opt-in](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in):
  consent and approved message purposes remain required; a timestamp does not prove consent.
- [Telnyx send WhatsApp](https://developers.telnyx.com/api-reference/whatsapp-messaging/send-a-whatsapp-message)
  and [official OpenAPI](https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json):
  POST `/messages/whatsapp` explicitly declares optional `Idempotency-Key`; UUIDv4
  is used internally. This is endpoint-specific, not an assumption about all APIs.
- [Telnyx idempotency](https://developers.telnyx.com/docs/development/api-fundamentals/idempotency):
  bounded 24-hour protection, scoped to organization/method/path with identical
  query and body bytes. Successful 2xx responses can be replayed; in-progress
  409/10036 and changed-request 422/10027 differ. Expiry can execute a new operation.
  A status number alone, timeout, 429 or generic 5xx does not prove non-submission.
- [Telnyx echo](https://developers.telnyx.com/api-reference/callbacks/whatsapp-business-app-message-echo)
  does not open/extend the service window. OpenAPI `MessagingInboundMessagePayload`
  describes `body.timestamp` as Meta-supplied Unix time; actual clock/provenance
  and live interoperability remain deployment gates, not proven by synthetic tests.

## Eligibility contract

Separate results: `free_form`, `approved_template`, `unproven`, `channel_blocked`,
and `operational_unknown`. Eligibility is an assessment, never an HTTP side effect.
Use only scoped, durably authenticated `inbound_event_receipts` from Ticket 07.
For each logical inbound use its FIRST receipt (lowest receipt id); later envelopes
cannot rehabilitate future/invalid first evidence or renew the source timestamp.
Require aware valid times `source <= event <= first_receipt <= now` and
`source <= now < source + 24 hours`. At exactly 24 hours deny. Missing/invalid,
contradictory, future evidence cannot open the window. Receipt, signature, ACK,
echo, status, edits/revokes, own replies and reconnect never substitute for source.
Replays do not renew it. Select the latest qualifying legitimate source.

A durable Telnyx local clock high-water mark prevents a backward clock correction
from reopening authorization after a later observation. Advance it only from the
local policy clock, including denied assessments; reject `now < high_water` and
future receipts. NTP correctness and a rollback that happened without an intervening
observation cannot be proved locally and remain CX-05. No permissive skew grace.

Consent is explicit, scoped to channel + Customer, time bounded, and separately
revocable. Store only an opaque evidence reference, timestamps and scope, no private
content. There is no consent acquisition UI or inference from merely receiving text.
Trusted synthetic fixtures may provision evidence; operational proof collection and
verification remain a future gate. A template assessment additionally requires
an approved, unexpired proof bound to channel, recipient, name/language and payload,
plus an authorized service-response purpose. Unproved/revoked/mismatched templates
and marketing/follow-up purposes deny. The current outbox contains free-form AI
Replies only: template classification does not convert body text to a template,
and no template dispatch or automatic fallback is introduced.

## Atomic authorization

Extend the existing BEGIN IMMEDIATE submission seam. All must hold together:
current owner + lease + started attempt, unmarked sending delivery, positive
channel verification, matching provider/channel/Customer/outbound/inbound identity,
valid policy/consent, unchanged payload binding, pause revision, no blocking handoff,
no delivery conflict or unresolved ordering barrier. Preserve the current episode's
authorized handoff confirmation exception. The same attempt can authorize only once.
Generic authorization cannot bypass the Telnyx policy; Telnyx legacy reply is denied.
The runner must supply the exact claimed OutboundMessage and durable submission key.
Expose a structured offline assessment for the future sender and keep the existing
bool seam compatible for Meta/Twilio. Assessment does not consume submission authority;
authorization repeats it in the writer transaction immediately before marking.

Commit the existing `submission_started_at`, first logical submission time and
attempt marker atomically. Never hold SQLite across network or LLM. Authorization
to actual HTTP remains CX-06: a later pause, expiry or disconnect cannot recall an
already authorized call. This ticket adds no sender and makes no exactly-once claim.

## Durable identity and outcomes

One random UUIDv4 submission key per logical Telnyx Outbound Delivery, assigned at
creation (backfilled on migration), retained on technical retry and restart. A new
delivery has a new key even if numeric SQLite ids are reused. Bind canonical
provider/channel/recipient/modality/body with a versioned fingerprint; compare on
each authorization and reject key/payload collisions. Keys and binding are immutable.
The fingerprint is private metadata, never logged. It is NOT proof that future
HTTP bytes are identical: Ticket 11 must bind deterministic method/path/query/body
bytes and organization before enabling the external idempotency guarantee.

Conservative V1 retry contract: local proof `not_submitted` may make a currently
owned unmarked attempt retryable. After a submission marker, an unqualified
retryable assertion, timeout or lost response becomes `unknown`. No HTTP response
allowlist is enabled in this ticket, because the future adapter must verify the
documented response and exact request before claiming safe retry. A repeated attempt
is not a new delivery, and a new key is never a remedy for an ambiguous outcome.
409/10036 indicates an operation in progress (unknown locally); 422/10027 is a
blocking key/request conflict; other 409/422 are not assigned these meanings.
Expose deterministic response-policy classifications using explicit synthetic
evidence, never fabricate observed HTTP results.

The external guarantee is conservatively unavailable at `first_submission + 24h`
or later and on backward/invalid time. It never grants permission to retry unknown.
Historical attempts lacking submission proof must not gain an invented guarantee;
preserve uncertain history and fail closed. Preserve every existing delivery state,
attempt, early callback and status ledger. Acceptance reconciliation remains in its
existing transaction. No event promotes unknown to pending/retryable.

## Persistence and validation

Migration 0021 is additive over 0020: stable delivery identity/fingerprint/first
submission time, per-attempt marker/retry evidence, scoped consent and local clock
high-water. Do not rebuild parent tables or change Meta/Twilio behavior. Require
new schema components in local structural checks. Protect immutable fields and
replacement paths; preserve maintenance/backup semantics. Downgrade by explicit
backup restore. Preserve pause revision, ownership, lease, lifecycle and handoff.

Use synthetic fixtures and real SQLite. Cover <24h / exactly24h / >24h, malformed
and contradictory time, skew and clock correction, ignored operational events,
legitimate inbound/replays, consent/templates, blocked/reconnected channel,
pause/resume/handoff/status conflict, concurrent authorization, stable keys/new
delivery/key-payload collision, pre/post possible-submission timeout, crash/restart,
external expiry, unknown no resend, rollback/0020 upgrade/restore and privacy.
Run complete pytest with network denied, Ruff check/format, compileall, pip check,
diff check, Gitleaks and independent Standards/Spec reviews; correct all P1/P2 and
repeat regressions. Record exact counts/skips and distinguish local evidence from CI.

Update issue #11 without closing risks absent orchestrator approval. Revalidate
CX-06,11/33,13,15,16,17,19,24/29/30,32,34. New CX-35+ must include origin, severity,
owner, gate and closure evidence. Normal push only of this isolated branch.
Delivery includes A–M report, final SHA, diff/files, verified contracts, matrices,
tests, reviews, limitations and issue link. Ticket11 requires new direct audit and
explicit authorization.
