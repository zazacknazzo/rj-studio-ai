# V1 Agentic Surface — Phase 1

Status: approved

Approval source: product-owner instruction of 2026-10-04, “STATE AND AUTHORITY
= DETERMINISTIC / CONVERSATION AND STRATEGY = LLM”. This incremental experiment
amends conversational restrictions of V1/Polish and ADR 0007 only for the new
surface; ADR 0009 remains proposed pending validation. Phase B remains paused.

## Scope and test seams

First version behavioral live oracles for all 53 cases, retaining injected
adversarial and structural contracts separately. Do not rescore historical runs.
Then extend the provider-neutral decision with bounded conversational parts,
purpose and optional preference targets, retaining FactReplyPart and legacy
PhraseReplyPart. Test decision/finalizer, MessageResponder with SQLite, intake
state, provider schema contracts and eval scoring using deterministic fakes.

The model chooses wording, ACK, CTA, timing, collection order and cancellation
recovery wording. A part's purpose is observability, not a sentence selector.
Question targets must be allowed and missing after preference merge. Multiple
related targets in one Message count as one committed qualification question.
Known preferences cannot be overwritten by invented excerpts. No-question turns
must preserve preferences without consuming budget or forcing another question.

## Hard limits

Approved facts/qualifiers and mandatory policies render from trusted sources.
Refs and claims remain validated. No booking, availability, cancellation,
payment or discount action capability is introduced. Model-only handoff remains
advisory; existing trusted safety and mandatory terminal policies take priority.
Complete appointment preferences or exhausted three-question budget after the
answer require durable handoff. Firm cancellation/refusal and confirmation or
unclear response after the single recovery offer require handoff; rescheduling
continues within the same budget. Recovery may be offered once, never replayed.
Core enforces state/ownership/ordering/privacy/outbox/accounting unchanged.

Conversational prose is not an alternative fact channel. Bounded post-generation
guards reject known protected-domain assertions and untrusted numeric/financial
values; they do not constitute a universal semantic proof. Source rendering and
real-action authorization remain deterministic. Undeclared nonnumeric claims
outside those guards are a residual experimental risk, not an approved fact or
capability. Document that limitation and keep live gates/human review open.
Minor wording, CTA, length/emoji style choices are soft; identity truthfulness,
sensitive safety and hard response bounds remain protected. No CoT is recorded.

## Validation and operational scope

Run requested adversarial/behavior/state tests, complete suite and existing
static checks. Obtain independent product, safety, architecture/standards and
eval reviews. Only then a fresh synthetic OpenAI smoke: ten existing cases,
gpt-6.1-sol, medium, default tier, output 512, observation 30s, no retries,
US$1 cap. No Anthropic, Meta/WhatsApp, real Customer or Phase B. Preserve usage,
cost, latency gates and old evidence. If smoke passes, prepare qualitative
human review without automated naturalness grades. Ticket 12 stays in-progress.

No CRM, agenda integration, notifications, multi-agent runtime, new database,
SaaS or messaging redesign. Legacy surface stays readable and retains its
previous behavior; record its future removal gate after human approval.
