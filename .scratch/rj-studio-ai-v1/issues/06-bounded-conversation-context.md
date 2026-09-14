# 06: Build bounded Conversation Context

**What to build:** Generated replies receive relevant recent Conversation history and selected Salon Knowledge without unbounded context growth or persistent Customer memory.

**Blocked by:** 02: Deliver ordered, deadline-bound webhook generation; 05: Load approved Salon Knowledge.

**Status:** ready-for-agent

## Context

V1 needs continuity for a recent exchange while retaining only the current Conversation history already held by V0.1.

## Likely components

Conversation history query/index, context builder, generation provider request input, token estimator/budgeting, and deterministic fake-provider tests.

## Acceptance criteria

- [ ] The builder includes at most 12 prior Messages no older than 30 days, with history near 2,000 tokens and total LLM input near 4,000 tokens.
- [ ] Current inbound and selected approved knowledge take precedence; deterministic trimming removes the oldest history first.
- [ ] A later ordered Message can observe state persisted by its predecessor when it remains in budget.
- [ ] Missing or trimmed context leads to clarification rather than an unsupported assumption.

## Required tests

- [ ] SQLite/FastAPI tests with the deterministic fake prove history order, 30-day cutoff, 12-Message cap, token trimming, and priority of inbound/knowledge.
- [ ] Synthetic context cases cover recent reference, topic change, truncation, and return after days.

## Non-goals

- Persistent summaries, Customer profile, preferences, Lead Stage, CRM memory, or cross-provider identity.
