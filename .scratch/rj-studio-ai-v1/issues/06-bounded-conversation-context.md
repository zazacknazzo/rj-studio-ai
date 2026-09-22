# 06: Build bounded Conversation Context

**What to build:** Generated replies receive relevant recent Conversation history and selected Salon Knowledge without unbounded context growth or persistent Customer memory.

**Blocked by:** 02: Deliver ordered, deadline-bound webhook generation; 05: Load approved Salon Knowledge.

**Status:** done

## Context

V1 needs continuity for a recent exchange while retaining only the current Conversation history already held by V0.1.

## Messaging architecture amendment

The original Ticket 06 implementation remains complete for the synchronous
baseline. ADR 0006 corrects its visibility rule: persistence of an AI Reply no
longer proves Customer visibility. Messaging Migration 03 and 05 own the
follow-up implementation.

- Include assistant speech only when its Outbound Delivery is `accepted`,
  `sent`, `delivered`, `read`, or explicitly `accepted_legacy`.
- Exclude `pending`, `sending`, `retryable`, `unknown`, `failed`, and
  `cancelled` replies from Conversation Context.
- If an accepted delivery later reports `failed`, do not rewrite context
  already consumed; block future automation for recovery or policy.
- Preserve current inbound priority, chronological order, age/count limits, and
  token budgets.
- Required follow-up tests cover every delivery state, legacy backfill, an
  accepted-then-failed status, and a later inbound that must not observe an
  unaccepted predecessor reply.

## Likely components

Conversation history query/index, context builder, generation provider request input, token estimator/budgeting, and deterministic fake-provider tests.

## Acceptance criteria

- [x] The builder includes at most 12 prior Messages no older than 30 days, with history near 2,000 tokens and total LLM input near 4,000 tokens.
- [x] Current inbound and selected approved knowledge take precedence; deterministic trimming removes the oldest history first.
- [x] A later ordered Message can observe state persisted by its predecessor when it remains in budget.
- [x] Missing or trimmed context leads to clarification rather than an unsupported assumption.

## Required tests

- [x] SQLite/FastAPI tests with the deterministic fake prove history order, 30-day cutoff, 12-Message cap, token trimming, and priority of inbound/knowledge.
- [x] Synthetic context cases cover recent reference, topic change, truncation, and return after days.

## Non-goals

- Persistent summaries, Customer profile, preferences, Lead Stage, CRM memory, or cross-provider identity.
