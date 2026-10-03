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

- 2026-10-03 usage provenance instrumented at d56d764. 634 tests / all checks
  pass; both independent review axes have no findings. The single authorized
  probe proved HTTPX read_timeout (class F), not API USAGE_ABSENT: no usable
  Response returned, no usage validation. Original failure remains unrecoverable
  because its primary error was overwritten. Exact cost unknown, reservation
  US$0.0112425; no retries, full smoke or B. Multi-intent correction and runtime
  unchanged. See docs/evals/V1/usage-diagnostic-2026-10-03.md.
  Ticket remains in-progress; grounding-multiple-facts is not evaluable.

- 2026-10-03 shared reply-plan instruction correction committed at 1faf390;
  both adapters use the same rule, no finalizer/schema/Knowledge changes.
  600 tests and checks pass; both review axes have no findings. One authorized
  live retest stopped on live_usage_missing_or_invalid: no valid model reply,
  usage/cost indeterminate, conservative reservation US$0.0112425, no retries.
  Full smoke and B NOT executed. See
  docs/evals/V1/multi-intent-instruction-correction-2026-10-03.md.
  Ticket remains in-progress; no claim of corrected live behavior.

- 2026-10-03 authorized single-case diagnosis reproduced multi-fact failure: both
  facts selected, price/hours Intents correct, but model omitted factual parts and
  refs. Classification MODEL_PLAN_INCOMPLETE; finalizer correctly imposed
  missing_critical_fact handoff. One paid call, US$0.0049335, no retries/B.
  See docs/evals/V1/multiple-facts-diagnostic-2026-10-02.md. 585 tests/checks pass;
  prompt correction proposed only. Ticket remains in-progress.

- Product-owner correction: repeat all ten smoke cases with medium reasoning,
  standard tier and output limit 512; model replies and local safe fallbacks
  have separate denominators. Historical run unchanged; no persona score for
  incomplete generation. See `docs/evals/V1/openai-smoke-512-2026-10-02.md`.
  Executed at `dcb6fdc`: 10 calls/valid decisions, no incomplete/paid failures,
  US$0.0296662. Multi-fact final response triggered unexpected handoff; two
  critical checks failed (2/18). B not executed; no further paid call after
  stop. 573 tests and all required checks passed; both review axes approved
  after the preflight fallback-count fix. Human/operational gates pending;
  ticket remains in-progress, comparison deferred.

- OpenAI-only partial live gate executed 2026-10-02: Phase A stopped at case
  `persona-incomplete-context` after 9/10 calls (`incomplete`, 200 output tokens);
  B not executed. Usage/accounting valid: US$0.0239327 total, one paid failure,
  no retries, 0/16 critical failures. Human packet has eight unscored answers.
  Full details/private record paths: `docs/evals/V1/openai-partial-2026-10-02.md`.
  This is not V1 approval. Comparative criteria remain unchecked; comparison
  deferred, further live coverage and human/operational review pending.
- Post-execution validation: 569 tests passed (15 new eval tests), Ruff check,
  format check, compileall, pip check and diff check passed. Independent Standards
  and Spec reviews approved the collector after the recorded fixes. One existing
  Starlette/AnyIO deprecation warning remains. No production code was changed.

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
