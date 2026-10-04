# V1 Agentic Surface — Phase 1

Date: 2026-10-04. Incremental implementation experiment. Independent reviews
and functional smoke passed; official latency failed and human approval is pending. ADR 0009 proposed; Ticket 12 in-progress;
Phase B paused. Baseline `7e3fc975b4de8d0ba0c74c1d52efb992586cc4fd`.

## Old and new boundary

Before: model selected PhraseReplyPart/FactReplyPart; core supplied fixed intake
questions and often added ACK/CTA. Now: provider-neutral ConversationalReplyPart
has bounded text, purpose and preference targets. `surface=agentic` prefers the
new path; default legacy remains readable. FactReplyPart still inserts only
approved statements; model reply_text is never authoritative customer output.

The model chooses greeting, ACK, CTA, social wording, timing, missing-field order,
related combined questions and recovery wording. Purpose describes a speech act;
it does not select a sentence. Core supplies trusted field-presence/constraints;
actual Customer preferences remain untrusted context. A social turn can preserve
preferences without asking or spending question budget. Soft human attention is
not terminal durable handoff and remains deferred.

## Deterministic authority retained

Refs/claims, exact approved fact values/qualifiers and mandatory policies remain
validated. Combined untrusted prose is checked across part boundaries. A small
veto covers known numeric/financial, official-hour, availability/action,
operational/policy/technical assertions; it is not a conversational planner.
Numeric day/time preference questions are not claims of official availability.
No availability, booking, cancellation, payment or discount tool/action is added.
Provider acceptance, messaging, ownership, ordering and outbox are unchanged.

Allowed missing targets and remaining budget authorize question effects. Only
retained authorized parts consume persisted budget. Recognizable undeclared
preference questions cannot evade the counter by being labeled CTA. Three
questions and one recovery remain hard. Complete preferences, exhausted budget,
firm cancellation/refusal and existing critical safety/human-request policies
require trusted durable handoff. Model-only Intents/handoff are advisory.

Migration `0012_agentic_intake` rebuilds only the lifecycle check: collecting may
have zero questions and no awaited field; existing data/FKs/recovery bounds and
terminal constraints remain. No new table/column or migration mechanism.

## Evals and observation

[All 53 classifications](../evals/V1/agentic-classification-2026-10-04.md) distinguish
behavioral paid observation, injected adversarial contracts and structural tests.
Oracle v3/live-record v8 identify future runs. Historical files/scores are
immutable. Persisted-state corruption is critical; wording/style variability is
not a critical STOP. Latency/billing gates remain unchanged. Phase B requires
separate authorization. New human packets request qualitative review, not grades.

Allowlisted trace records purposes, proposed/authorized/denied targets, refs,
rendered fact IDs and authorized handoff/actions. No prose, hidden reasoning or
raw provider payload is added to the trace; synthetic human packets retain the
final customer output for review.

## Residual risk and legacy exit

Trusted rendering proves the source of inserted fact segments. Finite guards
cannot prove absence of every nonnumeric protected assertion in free prose.
Disguised assertions and declared-target versus actual-speech mismatches remain
experimental semantic risks; purpose/Intent is not proof. This is not a guarantee
of universal critical-fact exclusion. No real action authority is granted.
Pilot approval must explicitly assess this limitation using live/human evidence.
Numeric preference statements outside bounded questions remain conservative.

Legacy phrase surfaces remain for compatibility, identity, safety and fallbacks.
Normal greetings, ACK, help, service/detail questions and commercial continuation
need no catalog wording on the new path. Remove legacy normal composition only
after human approval and provider-schema/regression evidence. Do not remove
trusted safety confirmations with it.

Larger shared instructions still use the existing approximate context overhead;
measure real provider token consumption. Anthropic's existing output cap remains
unchanged and has no live validation for this schema. Real Meta smoke is blocked
on App Secret. No Anthropic, real messaging, real Customer or Phase B is authorized.

## Validation

Offline validation: **890 tests passed**, including **59 new tests** across
surface, intake, behavioral oracle and migration seams. Ruff check/format,
compileall, pip check and diff check passed. All 396 historical evidence files
match their pre-change SHA-256; no rescore occurred.

Four independent reviews passed after corrections:

| Review | Findings corrected |
| --- | --- |
| Product/spec | Preserve ordinary social/CTA questions and numeric time preferences without consuming budget |
| Safety | Guard split assertions, preserve trusted appointment-change handoff, reject counter bypass |
| Architecture/standards | Reconcile retained question/recovery parts before durable completion |
| Eval behavioral | Source/target/state checks, critical persistence gate, known-field wording tolerance, qualitative packet |

The [new live smoke](../evals/V1/agentic-surface-smoke-2026-10-04.md) passed
10/10 cases, with 0/19 critical checks failed and US$0.0457838 spent. No retries
or paid failures. p95 observed E2E 10.930s fails the unchanged 8s gate. Two
noncritical generic clarification fallbacks remain visible for human review;
no post-smoke prompt/runtime change was made. The
[qualitative packet](../evals/V1/agentic-surface-human-review-2026-10-04.md)
contains exactly those ten observed responses. Product approval and real-provider
operation remain pending; this does not resume Phase B.
