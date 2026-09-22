# 03: Add durable Outbound Delivery and transactional outbox

**Status:** ready-for-agent

## Objective

Persist customer delivery independently from AI Reply generation and provide a
deterministic provider-neutral delivery `run_once` seam using the fake sender.
No real provider request is enabled yet.

## Invariants

- One AI Reply per inbound and one Outbound Delivery per AI Reply.
- Proactive completion atomically inserts AI Reply, pending delivery, and completed processing.
- Historical replies are never queued for resend; only evidence-backed rows become accepted_legacy.
- Only the current unexpired delivery owner can finalize an attempt.
- `unknown` is never automatically retried and blocks the Conversation.
- Provider Acceptance, not AI Reply persistence, is the same-Conversation progress boundary.

## Dependencies

- 01: Provider contracts and fake sender.
- 02: SQLite durability gate.

## Exact scope

- Add `outbound_deliveries` with pending, sending, retryable, unknown, accepted, sent, delivered, read, failed, cancelled, and accepted_legacy states.
- Add delivery owner token, lease, attempt count, next-attempt time, channel/recipient routing, provider Message ID, safe error metadata, and timestamps.
- Add minimal `delivery_attempts` evidence needed to reason about retry/unknown outcomes without storing payloads or Message bodies.
- Add database constraints/indexes for one delivery per AI Reply, provider ID uniqueness, valid claim shape, due work, and Conversation order.
- Backfill evidence-backed existing outbound Messages as `accepted_legacy`; classify every unverified legacy reply as `unknown` with a safe legacy-unverified reason. Never backfill pending.
- Add a redacted explicit reconciliation operation that can mark a legacy-unverified row accepted_legacy or cancelled without sending it.
- Add atomic proactive completion and a legacy completion path that records `accepted_legacy` while synchronous TwiML remains active.
- Add provider-neutral claim/finalize operations and deterministic `run_once` using the fake sender; do not start a background loop.
- Filter Conversation Context so only accepted/sent/delivered/read/accepted_legacy replies are assistant speech.
- Block later same-Conversation processing behind pending/retryable/sending/unknown/failed delivery as specified by ADR 0006.

## Out of scope

- Twilio REST, status webhooks, automatic executor lifecycle, early ACK, Meta, Human Handoff implementation, or automatic reconciliation of unknown outcomes.

## Migrations

- One conventional Alembic revision for delivery tables, constraints, indexes, and legacy-safe backfill.
- Create delivery rows and complete the legacy classification before tightening any trigger that requires a delivery for completed processing; migration failure must roll back without a partially enforced lifecycle.
- Migration tests use populated normal-webhook and manual-recovery `d4a104f` fixtures and prove no Message/reply loss, zero pending historical deliveries, and no false acceptance of unverified recovery replies.
- Downgrade must never cause already-proactively-sent work to be replayed through TwiML; document the safe downgrade boundary even if destructive downgrade is unsupported.

## Required tests

- Fresh migration and populated-baseline migration.
- Atomic success and injected rollback between AI Reply, delivery, and processing completion.
- Unique delivery under sequential/concurrent completion.
- Delivery owner, stale-owner, lease-expiry, restart, and attempt constraints; an expired sending lease becomes unknown and cannot be reacquired automatically.
- Accepted, retryable, permanent, and unknown fake-sender outcomes.
- Unknown receives no later automatic claim.
- Same-Conversation barrier and cross-Conversation independence.
- Context visibility for every delivery state and accepted-then-failed blocking.
- Retention/purge cannot remove nonterminal delivery work or required linkage.

## Crash cases

- Crash before atomic completion leaves no reply/delivery and permits safe regeneration.
- Crash after atomic completion leaves pending durable delivery.
- Crash after acquiring/sending state but before known finalization becomes unknown at lease expiry, even if the fake proves the call had not started; availability is traded for duplicate prevention.
- Crash after simulated acceptance but before local finalization remains unknown/ambiguous and receives no automatic resend.

## Definition of Done

- Schema and store enforce all invariants without in-memory correctness locks.
- Deterministic `run_once` is the test interface for one delivery attempt.
- Real provider sending remains impossible in the default runtime.
- Full tests, migrations, Ruff, and static checks pass.

## Rollout and rollback

- Deploy in legacy mode; new successfully rendered synchronous replies record the explicit legacy equivalent. Reconcile pre-migration unknown rows before allowing their Conversations to continue.
- Keep automatic delivery disabled until Ticket 04 cutover.
- Before rollback, confirm there are no proactive pending/sending/unknown rows; otherwise rollback is blocked pending operator resolution.
