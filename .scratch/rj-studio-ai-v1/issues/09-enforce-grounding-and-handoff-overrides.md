# 09: Enforce grounded factual replies and trusted overrides

**What to build:** Before an AI Reply is sent, application code validates critical claims against approved Salon Knowledge and applies mandatory Human Handoff rules even when the LLM proposes otherwise.

**Blocked by:** 05: Load approved Salon Knowledge; 07: Produce validated Intent decisions; Messaging Migration 01–05.

**Status:** blocked

## Context

LLM output is an untrusted proposal. A correct model `knowledge_ref` does not prove that the free-text reply states the correct price, hours, Service, Professional, policy, or availability.

The implementation must be redesigned after the messaging migration. Prefer
typed reply segments backed by trusted facts for critical customer-visible
content instead of treating model-emitted `critical_claims` as the sole
grounding mechanism. The policy runs before atomic AI Reply + Outbound Delivery
finalization and must not bypass delivery or Human Handoff eligibility.

## Likely components

Trusted factual-claim validator, deterministic critical-value composition, handoff policy evaluator, application response finalizer, and grounding/uncertainty eval fixtures.

## Acceptance criteria

- [ ] Critical customer-visible claims are matched to selected approved knowledge or trusted integration output before sending; conflicting or unsupported free text is safely corrected or blocked.
- [ ] Unknown or unavailable facts yield concise clarification, redirection, or Human Handoff and never an invented salon fact or availability promise.
- [ ] Trusted state and policy override a model’s `handoff=false`, including active handoff, `requires_human_consultation`, mandatory Service/policy rules, and approved deterministic conditions.
- [ ] Customer Message text cannot alter trusted facts, policy, or handoff rules.

## Required tests

- [ ] Test that a correct knowledge reference plus divergent textual price is corrected or blocked before the provider response.
- [ ] Test unknown price/policy/Service/Professional/availability, false Customer salon claim, and prompt-injection attempt.
- [ ] Test a Service requiring human consultation when the LLM proposes `handoff=false`.
- [ ] Add synthetic grounding, uncertainty, technical-risk, and mandatory-handoff eval cases.

## Non-goals

- Second reviewing LLM, generic fact-checking service, RAG infrastructure, schedule lookup, or real Appointment confirmation.

## Comments

- Commit `55919a7` implemented the earlier Ticket 09 design on the preserved
  local branch `codex/v1-grounding-policy-overrides`. It is intentionally
  excluded from the `d4a104f` messaging-migration baseline and must not be
  merged or cherry-picked wholesale. Review it later for reusable tests and
  policy cases after Messaging Migration 01–05; do not discard or rewrite it.
