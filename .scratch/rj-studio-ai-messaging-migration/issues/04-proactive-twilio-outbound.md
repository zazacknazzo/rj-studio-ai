# 04: Deliver proactively through Twilio REST

**Status:** done

## Objective

Activate provider-neutral outbound execution with a minimal Twilio REST sender,
durable delivery claims, and Twilio status callbacks while retaining a safe,
mutually exclusive legacy/proactive rollout mode.

## Invariants

- One runtime mode owns customer delivery: legacy TwiML or proactive REST, never both.
- Only the current delivery owner can submit/finalize.
- A successful REST response with provider Message ID becomes accepted, not delivered/read.
- Definitively retryable failures use bounded backoff; unknown outcomes never auto-retry.
- A blocked delivery affects only its Conversation.
- Before submit, revalidate owner, eligibility, and the future Human Handoff seam.

## Dependencies

- 03: Durable outbox and delivery runner.

## Exact scope

- Implement minimal Twilio REST outbound sender behind the canonical interface.
- Add lifespan-managed outbound polling/wake-up with bounded configurable concurrency.
- Persist accepted provider Message ID and monotonic sent/delivered/read/failed callbacks.
- Authenticate and idempotently ingest Twilio status callbacks.
- Durably retain an authenticated status that arrives before its delivery can be correlated; merge it when local acceptance finalizes instead of acknowledging and losing it.
- Classify provider responses into accepted, retryable, permanent, or unknown without storing secrets/payloads. Retryable requires provider-contract evidence that acceptance did not occur; timeout, connection loss, malformed response, and undocumented error semantics are unknown.
- Implement bounded retry/backoff for definitive retryable outcomes.
- Block and expose unknown, terminal failure, and accepted-then-failed Conversations for recovery/policy.
- Add an explicit mutually exclusive delivery mode. Proactive mode returns acknowledgement-only TwiML and creates pending deliveries; legacy mode renders the reply and records accepted_legacy.
- Add privacy-safe delivery latency/outcome metrics.

## Out of scope

- Async LLM processing, early ingress ACK, Meta, automatic unknown reconciliation, Human Handoff state, notification system, or provider-independent production failover.

## Migrations

- Add only fields/indexes and a minimal unmatched-status inbox proven necessary by the implemented Twilio callback race. Do not redesign the Ticket 03 lifecycle.

## Required tests

- Twilio sender contract for accepted, retryable, permanent, timeout/connection-unknown, and malformed response.
- One active claim under concurrent outbound executors and restart recovery after lease expiry.
- Duplicate and out-of-order status callbacks do not regress evidence.
- A status callback that beats local acceptance commit is retained and later merged exactly once.
- Provider Acceptance releases the Conversation barrier without waiting for delivered/read.
- Accepted then failed blocks future automation without rewriting prior history.
- Unknown is visible, has no automatic retry, and blocks later same-Conversation work.
- Legacy mode never calls REST; proactive mode never embeds an AI Reply in TwiML.
- Redacted end-to-end Twilio Sandbox smoke covers proactive delivery and status.

## Crash cases

- Crash after acquiring `sending` but before or during the REST call becomes unknown at lease expiry; it is not automatically resubmitted because the durable state cannot prove the call did not start.
- Crash after definitive rejection: retry follows persisted policy.
- Crash/network loss after possible provider acceptance: record/derive unknown and do not auto-resend.
- Crash after accepted result but before local commit remains an unavoidable ambiguity; tests and docs must not claim exactly once.
- Status callback before local acceptance finalization is merged idempotently by provider Message ID when possible or quarantined safely.

## Definition of Done

- Proactive Twilio outbound works through the canonical sender and durable executor.
- New smoke evidence records commit, date, expected/observed behavior, and no secrets/PII.
- Legacy and proactive paths cannot both deliver one reply.
- Full tests, Ruff, static checks, and code review pass.

## Rollout and rollback

- Deploy schema/code in legacy mode first, verify readiness, then switch one process to proactive mode.
- At cutover, verify no second process and no mixed delivery mode.
- Rollback to legacy only after outbound acquisition is stopped and pending/sending/unknown rows are drained, cancelled, or explicitly reconciled; never render those same replies again via TwiML.
