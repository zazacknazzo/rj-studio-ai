# 01: Add durable generation claims

**What to build:** The application can durably represent one inbound Message's LLM-processing lifecycle, so a future generated reply is coordinated correctly across retries and process restarts.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

## Context

V0.1 already persists one inbound and one reply. V1 needs a SQLite-backed claim before a slow, non-deterministic LLM call can safely replace the fixed reply.

## Likely components

Alembic migration, SQLite Conversation store, canonical generation/processing records, and persistence integration tests.

## Acceptance criteria

- [ ] The V0.1-to-V1 migration preserves fixture Conversations, inbound Messages, and linked replies without data loss.
- [ ] Each inbound Message has one durable processing lifecycle supporting `processing`, `retryable`, `completed`, and terminal `suppressed`; `suppressed` never requires an AI Reply.
- [ ] A generation claim records an owner token, 30-second lease, and no more than two attempts; only its current owner may complete it.
- [ ] Concurrent and stale owners cannot create a second logical AI Reply or overwrite a later owner’s result.
- [ ] The persistence finalization boundary can atomically record a terminal inbound result and one AI Reply, while leaving a seam for V1.6 to add Conversation handoff state in the same transaction.

## Required tests

- [ ] Migration test from a populated V0.1 fixture.
- [ ] SQLite tests for concurrent claim acquisition, lease expiry after restart, stale-owner rejection, attempt limit, and reply uniqueness.
- [ ] SQLite test that `suppressed` is terminal and has no outbound reply.

## Non-goals

- Calling an LLM, changing webhook behavior, Human Handoff workflow, queues, Redis, or multi-instance coordination.
