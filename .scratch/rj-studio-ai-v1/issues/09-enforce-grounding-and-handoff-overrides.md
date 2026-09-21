# 09: Enforce grounded factual replies and trusted overrides

**What to build:** Before an AI Reply is sent, application code validates critical claims against approved Salon Knowledge and applies mandatory Human Handoff rules even when the LLM proposes otherwise.

**Blocked by:** 05: Load approved Salon Knowledge; 07: Produce validated Intent decisions.

**Status:** done

## Context

LLM output is an untrusted proposal. A correct model `knowledge_ref` does not prove that the free-text reply states the correct price, hours, Service, Professional, policy, or availability.

## Likely components

Trusted factual-claim validator, deterministic critical-value composition, handoff policy evaluator, application response finalizer, and grounding/uncertainty eval fixtures.

## Acceptance criteria

- [x] Critical customer-visible claims are matched to selected approved knowledge or trusted integration output before sending; conflicting or unsupported free text is safely corrected or blocked.
- [x] Unknown or unavailable facts yield concise clarification, redirection, or Human Handoff and never an invented salon fact or availability promise.
- [x] Trusted state and policy override a model’s `handoff=false`, including active handoff, `requires_human_consultation`, mandatory Service/policy rules, and approved deterministic conditions.
- [x] Customer Message text cannot alter trusted facts, policy, or handoff rules.

## Required tests

- [x] Test that a correct knowledge reference plus divergent textual price is corrected or blocked before the provider response.
- [x] Test unknown price/policy/Service/Professional/availability, false Customer salon claim, and prompt-injection attempt.
- [x] Test a Service requiring human consultation when the LLM proposes `handoff=false`.
- [x] Add synthetic grounding, uncertainty, technical-risk, and mandatory-handoff eval cases.

## Non-goals

- Second reviewing LLM, generic fact-checking service, RAG infrastructure, schedule lookup, or real Appointment confirmation.
