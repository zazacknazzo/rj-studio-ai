# V1 Agentic Surface — Phase 1.1

Status: approved

Approval: product-owner instruction of 2026-10-04, Commercial Steering + General
Clarification. Phase 1 safety passed, but human conversational/product review is
not yet approved. This is an incremental correction, not a new commercial engine.

## Scope and seams

Separate general information gaps (service, Customer goal, clarification) from
appointment preference targets. General questions may render outside intake;
they create no intake/state/operational effect and spend no appointment budget.
Preserve existing scoped preference targets, cancellation recovery and trusted
terminal handoff. Missing/known appointment targets remain bounded and validated.
A service already present in collecting intake is not a general unresolved gap.

Use a small optional model-proposed next conversational action for planning and
allowlisted observation only. It authorizes no effect and selects no sentence.
The shared prompt teaches: understand, answer trusted information, identify the
most useful next step, continue when useful. Continuation remains soft and CTA
is optional. No new phrase catalog, deterministic commercial tree or auto-CTA.

Test public structured decisions, trusted finalization, responder/persisted
intake, provider schema compatibility and behavioral eval observations. Price
with/without continuation stays valid. Ambiguous commercial requests must have
an actionable, retained clarification rather than generic fallback. General
clarification is evaluated separately from critical factual safety; no LLM judge.

## Invariants and limits

FactReplyPart, refs/claims, approved policies, protected assertions, factual
relevance, safety and handoff authority remain. Model-only terminal handoff is
advisory. No booking/availability/payment/discount capability is added. Preserve
three committed intake questions, one recovery, ordering, outbox and ownership.
No migration, new persisted planning state, notifications, CRM, tools or messaging
change. Soft human attention is a proposal only, with no operational mechanism.
No secrets, real Customer data or CoT in evidence. Preserve historical runs and
the product owner's existing review annotations exactly.

## Validation

TDD for free clarification/steering plus existing regression seams; full suite,
Ruff check/format, compileall, pip check and diff checks. Four independent reviews:
product/commercial, agentic architecture, safety/invariants and eval behavioral.
Each asks whether this restores model reasoning or reintroduces a decision tree.

After checks/reviews, one synthetic run each for the existing direct-price,
ambiguous-price and discount cases: gpt-6.1-sol, medium, default tier, output 512,
observation 30s, zero retries, shared US$0.30 cap. Stop if any fails. Only if all
three pass, one new ten-case smoke with the unchanged US$1 smoke cap and a new
qualitative packet. No Anthropic, Meta/WhatsApp or Phase B. Do not optimize latency
or change production deadlines. The official latency gate remains 8s; product
approval is human-owned, ADR 0009 proposed and Ticket 12 in-progress.
