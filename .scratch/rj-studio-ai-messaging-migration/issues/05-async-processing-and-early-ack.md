# 05: Move AI processing behind durable ingress

**Status:** in-progress

## Objective

Make the webhook an ingress-only path and move generation into an automatic
durable Processing Executor, removing provider retry as the work scheduler.

## Invariants

- ACK occurs only after durable inbound/status commit.
- Every acknowledged eligible inbound remains discoverable after crash/restart.
- Same-Conversation processing and delivery preserve Provider Acceptance order.
- Different Conversations can progress concurrently.
- LLM work never runs in the webhook or inside a SQLite transaction.
- Existing generation owner/lease/stale-owner/idempotency guarantees remain.

## Dependencies

- 02: SQLite durability gate.
- 03: Durable outbox and delivery runner.
- 04: Proactive Twilio outbound.

## Exact scope

- Add a lifespan-managed Processing Executor with durable polling, optional in-memory wake-up, bounded configurable concurrency, and graceful shutdown.
- Persist/dedupe inbound and acknowledge immediately after commit.
- Remove bounded webhook wait, predecessor HTTP 503, synchronous LLM invocation, and reply rendering from ingress.
- Automatically reclaim retryable and expired generation claims; keep manual recovery for unknown/terminal operator cases.
- Separate ingress, processing, and outbound deadlines. Preserve the existing 10-second total attempt-sequence budget for one acquired processing execution and 30-second generation lease.
- Enforce Provider Acceptance/accepted_legacy as the predecessor visibility and progress boundary.
- Extend readiness with executor-loop health while making no external provider call.
- Preserve suppression acknowledgement behavior required by future Human Handoff.

## Out of scope

- Meta, Ticket 09 grounding redesign, Ticket 10 handoff state, Redis, external queue, generic scheduler, multiple application processes, or horizontal scaling.

## Migrations

- None unless a measured polling/ordering query requires an additive index. Reuse existing processing lifecycle and Ticket 03 delivery schema.

## Required tests

- ACK after commit and non-ACK on commit failure.
- Crash after ACK/before processing and successful restart recovery without provider retry.
- Same inbound concurrent retries create no second generation or delivery intent.
- Later same-Conversation inbound remains durable and unprocessed until predecessor Provider Acceptance.
- Different Conversations process while another waits on LLM or outbound.
- Processing deadline covers both LLM attempts together and is independent of ingress/outbound deadlines.
- Stale processing claims recover automatically; current owners cannot be preempted.
- Executor stop/start and readiness health are deterministic in tests without sleeps.
- FastAPI tests use deterministic drain/run_once seams and no longer expect response TwiML content or ordering 503.

## Crash cases

- Crash before inbound commit: no successful ACK; provider retry is required.
- Crash after commit before ACK: duplicate webhook dedupes; executor may already process.
- Crash after ACK before claim: polling finds the inbound.
- Crash during LLM: lease expiry permits a later owner; duplicate provider cost remains possible, duplicate logical reply does not.
- Crash after AI Reply/outbox commit: outbound executor continues.

## Definition of Done

- Webhook performs no LLM or outbound work and returns only provider acknowledgement after commit.
- No persisted eligible Message needs a provider retry to reactivate.
- Full suite, migration suite, Ruff, static checks, restart tests, and code review pass.
- Updated Twilio smoke proves early ACK followed by proactive reply.

## Rollout and rollback

- Enable only after Tickets 02–04 readiness and proactive smoke pass.
- Stop new processing acquisition during deploy; expired claims recover after restart.
- Rollback to synchronous processing is allowed only with proactive delivery retained and a reviewed plan for already-acknowledged pending inbounds; never restore TwiML delivery for rows already owning deliveries.
