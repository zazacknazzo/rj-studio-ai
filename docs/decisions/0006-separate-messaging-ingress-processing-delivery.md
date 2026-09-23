# Separate messaging ingress, AI processing, and outbound delivery

Status: accepted

The synchronous Twilio/TwiML path couples webhook acknowledgement, slow LLM
generation, and customer delivery. This can strand an already-persisted
Message when provider retries stop, cannot represent Meta Cloud API delivery,
and makes a persisted AI Reply look customer-visible before a provider accepts
it. Separate the pipeline into durable ingress, a processing executor, and an
outbound executor. SQLite remains the durable coordinator; no Redis, broker,
distributed worker system, or Postgres is introduced.

Ingress authenticates and normalizes provider events, commits inbound Messages
or delivery statuses, and only then acknowledges the webhook. Processing uses
the claims from ADR 0005 and, on success, atomically inserts the AI Reply, one
pending Outbound Delivery, and completed processing state. Outbound delivery
has its own owner token, lease, attempts, status, and provider Message ID. The
provider seam separates inbound acknowledgement from outbound submission;
Twilio is the development adapter and Meta Cloud API is the production target.

One logical AI Reply and one delivery intent are strongly unique locally.
External submission cannot be exactly once: a provider may accept a request
whose response is lost. Definitively retryable failures use bounded at-least-once
submission. An ambiguous result becomes `unknown`, receives no automatic retry,
and blocks automation for that Conversation until explicit reconciliation,
recovery, or Human Handoff. This prefers avoiding a duplicate customer-visible
Message over silently assuming either success or failure.

Retryable means the provider contract proves that no acceptance occurred.
Timeouts, connection loss, malformed responses, and undocumented failure
semantics are unknown rather than generically retryable.

An expired outbound `sending` lease is also ambiguous: the next owner cannot
know whether the previous process crossed the external submission boundary.
It becomes `unknown` instead of being reclaimed for automatic submission.

Conversation processing advances only after the previous Outbound Delivery is
provider-accepted, explicitly marked as its legacy equivalent, or explicitly
cancelled by an operator. Cancellation resolves the ordering barrier without
making the unsent AI Reply customer-visible. Acceptance means the provider
returned a durable Message identifier; it is not evidence of `sent`,
`delivered`, or `read`. A later asynchronous `failed` status does not rewrite
history already used by processing, but blocks future automation in the
Conversation pending policy or recovery.

Conversation Context may include an AI Reply as assistant speech only after
Provider Acceptance or explicit legacy acceptance. Pending, sending,
retryable, unknown, failed, or cancelled replies are not customer-visible
context. Before outbound submission, the executor revalidates delivery
eligibility, current owner, and Human Handoff policy so a future handoff can
cancel work not yet submitted.

Existing rows without durable delivery evidence cannot be inferred accepted.
Migration marks them unknown with a legacy-unverified reason; an operator may
explicitly reconcile a row to `accepted_legacy` when evidence supports it.
Historical rows are never backfilled as pending.

Early acknowledgement is allowed only after SQLite is configured and verified
with WAL, `synchronous=FULL`, foreign keys on every connection, a uniform busy
timeout, appropriate queue indexes, persistent local storage, and one active
application process. Readiness verifies the database settings it can observe;
deployment configuration enforces persistent storage and the single-process
constraint.

Messaging Migration 04 implements the outbound half of this decision. Twilio
Message creation is Provider Acceptance when a valid MessageSid is returned,
regardless of whether the initial Twilio status is `queued` or `accepted`.
Only documented HTTP 429 non-processing is automatically retryable. Only an
allowlist of documented terminal Twilio Message errors becomes `failed`;
undocumented 4xx, ambiguous transport, 5xx, and malformed-response outcomes
become `unknown`. A minimal
durable inbox closes the race in which an authenticated status callback arrives
before local MessageSid correlation. Messaging Migration 05 moves AI work to
durable SQLite polling and acknowledges inbound callbacks after persistence.
The Processing Executor reuses ADR 0005 claims and starts its own 10-second
attempt-sequence budget after acquisition. The legacy TwiML mode remains a
controlled rollback path; proactive ingress is gated by local readiness.
