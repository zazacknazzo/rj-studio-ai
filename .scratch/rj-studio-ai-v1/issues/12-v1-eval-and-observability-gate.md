# 12: Run the V1 eval and observability gate

**What to build:** V1 has a reproducible, privacy-safe evaluation record and Sonnet-versus-Terra comparison that can decide whether the completed AI Attendant meets its safety, quality, latency, and cost gates.

**Blocked by:** 03: Add the Claude provider and generation metrics; 04: Recover pending generated Messages explicitly; 05: Load approved Salon Knowledge; 06: Build bounded Conversation Context; 07: Produce validated Intent decisions; 08: Apply Lívia’s stable WhatsApp persona; 09: Enforce grounded factual replies and trusted overrides; 10: Make Human Handoff durable and atomic; 11: Collect appointment interest before handoff.

**Status:** in-progress

**Phase 1:** harness implemented / live model gate pending.
See [offline harness](../../../docs/evals/V1/harness.md). No paid calls, live-model
evals, paired human comparison or Meta smoke are authorized by this phase.

## Context

Evals complement deterministic webhook, SQLite, migration, and provider-contract tests. All cases must be synthetic or explicitly sanitized.

## Likely components

V1 eval case index and run records, eval runner/reporting, metric aggregation, model-comparison execution, and deterministic report validation tests.

## Acceptance criteria

- [x] The suite contains at least 28 synthetic or sanitized cases spanning grounding, hallucination, Intent, context, persona, uncertainty, prompt injection, technical risk, appointment behavior, and Human Handoff.
- [ ] Every run records case/run counts, model/configuration, critical failures, grounding, Intent, handoff, persona/naturalness, p50/p95 latency, input/output tokens, and estimated cost without full Message bodies, secrets, or unnecessary PII.
- [ ] Critical grounding and Human Handoff cases have zero prohibited claims; percentages name numerator, denominator, and run count.
- [ ] Sonnet and Terra are compared with equivalent input, knowledge, prompt, token budget, and configuration; important probabilistic cases run repeatedly and naturalness review is paired and preferably blind.
- [ ] The operational gates use every billable eval/smoke execution, including paid retries and token-consuming failures: p95 end-to-end latency is at most 8 seconds and estimated cost is at most US$10 per 1,000 completed AI Replies, unless an explicit evidence-backed threshold revision is recorded.

## Required tests

- [x] Deterministic tests reject invalid run records, unreported critical failure, real Customer fixture, missing denominator, and metric redaction failure.
- [x] Tests verify failed/retried paid attempts remain in latency/cost accounting and do not inflate the completed-reply denominator.

## Non-goals

- Automatic model switching, production alerting platform, external provider failover, real Customer conversations in fixtures, or authorization for autonomous production operation.

## Comments

- 2026-10-02 product-owner revision: Anthropic comparison deferred. Authorized
  OpenAI-only `gpt-6.1-sol`, Medium, standard, US$1 smoke / US$5 global cap.
  See `docs/evals/V1/openai-partial-2026-10-02.md`. Comparative acceptance stays
  unchecked, human review pending, ticket in-progress. No runtime provider change.

- Phase 1 indexes 52 synthetic cases (45 retained plus 7 context/handoff cases),
  validates versioned records and denominators, accounts for billable retries/
  token-consuming failures, aggregates and prepares blind pairs offline.
- Live provider collection, verified current model IDs/pricing, probabilistic
  repetitions, real E2E latency/cost evidence and human review remain Phase 2.
  No overall V1 gate or winner is claimed; this ticket is not done.
- Validation: 44 harness tests; full suite 554 passed. Ruff check/format,
  compileall, pip check and whitespace checks pass. One existing recovery test
  now explicitly isolates its legacy/fixed configuration from the local `.env`.
  Production M06/Tickets 09/10/11 and credentials remain unchanged.
