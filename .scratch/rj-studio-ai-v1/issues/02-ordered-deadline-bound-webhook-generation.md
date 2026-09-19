# 02: Deliver ordered, deadline-bound webhook generation

**What to build:** A non-factual inbound Message can receive one deterministic test-generated AI Reply through the existing webhook, with replay, per-Conversation order, and safe retry behavior visible at the HTTP seam.

**Blocked by:** 01: Add durable generation claims.

**Status:** done

## Context

This is the first complete generated-reply path. It uses a deterministic LLM fake so correctness of claims, ordering, deadlines, and provider rendering is testable before a real provider is introduced.

## Likely components

Webhook composition, application generation coordinator, narrow LLM test contract, SQLite store, and FastAPI integration tests.

## Acceptance criteria

- [x] One safe non-factual inbound creates at most one AI Reply; sequential or concurrent retries replay that exact durable reply.
- [x] Only one generation runs per Conversation while unrelated Conversations can generate in parallel.
- [x] A later Message is persisted before a bounded wait; when its predecessor remains active or its waiting budget is exhausted, the webhook returns retryable non-2xx with no customer-visible AI Reply.
- [x] The 10-second monotonic budget begins at inbound admission and covers SQLite waits, ordering waits, fake-provider work, retries, validation, final persistence, and response rendering; every stage consumes only remaining budget and finalization retains a margin.
- [x] No new generation attempt starts without useful remaining budget. Timeout, malformed result, and transient failure follow the safe retry/clarification path without invented salon facts.

## Required tests

- [x] FastAPI tests for normal reply, replay after restart, concurrent retry, ordered later Message, and unrelated Conversation parallelism.
- [x] Deterministic fake tests proving an accumulated SQLite/ordering wait prevents a late LLM call.
- [x] Tests for retryable ordering response, timeout, malformed result, and provider-rendering retry without duplicate persistence.

## Non-goals

- Claude, GPT-5.6 Terra, Salon Knowledge, customer memory, Human Handoff state, or automatic provider fallback.
