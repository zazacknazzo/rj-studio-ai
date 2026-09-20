# 04: Recover pending generated Messages explicitly

**What to build:** An operator can find pending or stale generated Messages and safely recover the oldest eligible one in its Conversation without relying on another provider retry.

**Blocked by:** 02: Deliver ordered, deadline-bound webhook generation.

**Status:** done

## Context

Provider retries can stop after an inbound has already been persisted. V1 deliberately uses an explicit local operation instead of adding a worker, queue, or Redis.

## Likely components

Maintenance command, SQLite recovery queries and claim transitions, generation coordinator, and integration tests.

## Acceptance criteria

- [x] A local operation lists pending or stale work without displaying Message bodies or customer addresses in routine output.
- [x] A manual retry operates only on the oldest eligible Message in a Conversation and reuses durable claim/idempotency rules.
- [x] Recovery records its terminal result and cannot produce a second AI Reply or process a later Message first.
- [x] The documented behavior makes clear that autonomous recovery requires a future executor and remains out of V1.

## Required tests

- [x] Crash simulation where provider retries exhaust, the stored Message is discoverable, and safe manual recovery succeeds.
- [x] SQLite and command tests for stale work, ordering protection, replay, and redacted routine output.

## Non-goals

- Automated scheduler/worker, queue, Redis, full Human Handoff operation, or external notification.
