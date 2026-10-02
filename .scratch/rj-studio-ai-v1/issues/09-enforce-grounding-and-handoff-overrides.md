# 09: Enforce grounded factual replies and trusted overrides

**What to build:** Before an AI Reply is sent, application code validates critical claims against approved Salon Knowledge and applies mandatory Human Handoff rules even when the LLM proposes otherwise.

**Blocked by:** 05: Load approved Salon Knowledge; 07: Produce validated Intent decisions; Messaging Migration 01–05.

**Status:** done

## Context

LLM output is an untrusted proposal. A correct model `knowledge_ref` does not prove that the free-text reply states the correct price, hours, Service, Professional, policy, or availability.

The redesign after M01–M06 uses typed reply parts backed by trusted facts
(ADR 0007). Model-emitted `critical_claims` are proposals, not the grounding
authority. The policy runs before atomic AI Reply + Outbound Delivery
finalization and does not bypass delivery eligibility. Durable Human Handoff
activation/suppression and its state checks remain Ticket 10.

## Likely components

Trusted factual-claim validator, deterministic critical-value composition, handoff policy evaluator, application response finalizer, and grounding/uncertainty eval fixtures.

## Acceptance criteria

- [x] Critical customer-visible claims are matched to selected approved knowledge or trusted integration output before sending; conflicting or unsupported free text is safely corrected or blocked.
- [x] Unknown or unavailable facts yield concise clarification, redirection, or a Human Handoff proposal and never an invented salon fact or availability promise.
- [x] Trusted policy overrides a model’s `handoff=false`, including `requires_human_consultation`, mandatory Service/policy rules, and approved deterministic conditions. Active handoff state enforcement is owned by Ticket 10 alongside its durable state.
- [x] Customer Message text cannot alter trusted facts, policy, or handoff rules.

## Required tests

- [x] Test that a correct knowledge reference plus divergent textual price is corrected or blocked before the provider response.
- [x] Test unknown price/policy/Service/Professional/availability, false Customer salon claim, and prompt-injection attempt.
- [x] Test a Service requiring human consultation when the LLM proposes `handoff=false`.
- [x] Add synthetic grounding, uncertainty, technical-risk, and mandatory-handoff eval cases.

## Non-goals

- Second reviewing LLM, generic fact-checking service, RAG infrastructure, schedule lookup, or real Appointment confirmation.

## Comments

- Validation: full suite 405 passed (one existing Starlette deprecation warning);
  48 grounding cases include 12 executable synthetic eval fixtures, restart/replay
  and deterministic outbound submission. Ruff check/format, compileall, pip check
  and git diff --check passed. Tests used process-only configuration overrides
  for legacy regression isolation and zero-cost test pricing; no local `.env`
  was inspected or changed. No live provider was contacted.
- Manual adversarial review covered undeclared/forged references, raw text
  without claims, wrong number/currency/duration, history/Customer injection,
  omitted Service rules, final-surface limits, transparency failures, atomic
  outbox/replay compatibility, and scope. Empty informational plans were changed
  to clarification. No blocking findings remain for this ticket. Residuals:
  approval/source correctness and lexical selection, bounded phrase naturalness,
  finite localized risk patterns, live model output/token/latency evals, and
  durable Human Handoff owned by Ticket 10. No real Salon Knowledge added.

- Resumed from M06 `b797b0f947d6b80b37591689614bff9961f43ff7` on
  `codex/v1-ticket-09-trusted-grounding`. No old Ticket 09 commits incorporated.
  The approved V1 Human Handoff requirement is unchanged: this ticket proposes
  human review without confirming a transfer; Ticket 10 owns persistence,
  suppression, release and atomic state/owner checks. No provider or messaging
  architecture change, migration, credential access, or real smoke is included.

- Commit `55919a7` implemented the earlier Ticket 09 design on the preserved
  local branch `codex/v1-grounding-policy-overrides`. It is intentionally
  excluded from the `d4a104f` messaging-migration baseline and must not be
  merged or cherry-picked wholesale. Review it later for reusable tests and
  policy cases after Messaging Migration 01–05; do not discard or rewrite it.
