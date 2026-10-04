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

## Phase 1.1 — Commercial Steering

Functional safety passing != product conversational quality passing. The product
owner reviewed Phase 1: case 1 was factual but dry; cases 2/4 ignored the request
after generic fallback; case 3 was accepted. Human conversational/product review
is **NOT YET APPROVED**. The remaining six cases were not used to reject it.

The approved [Phase 1.1 scope](../specs/V1-agentic-surface-phase-1.1.md) adds
commercial goals and general gaps without restoring deterministic wording.
Case 1 lacked sufficient soft commercial steering. Cases 2/4 proposed service
questions, but preference targets required active intake; parts were dropped and
the local empty-render fallback substituted. General clarification and durable
appointment collection must have separate scopes.

### Phase 1.1 boundary

`conversation.information_targets` describes general gaps: `service`,
`customer_goal`, `clarification`. It is mutually exclusive with appointment
`targets` and allowed only for question/clarification parts. Outside intake it
creates no preferences, episode or budget charge. Inside intake, recognizable
preference requests must retain authorized appointment targets; known service
questions are vetoed using persisted intake or a validated current Customer
excerpt. Selected Knowledge alone never proves Customer service choice. Ordinary
goal questions do not spend the appointment question budget.

`next_action` is an optional five-value planning proposal: answer only, clarify,
continue conversation, social response, request human attention. It chooses no
wording, authorizes no effect and adds no state machine. Soft human attention is
only semantic preparation; no notification, queue or persisted flag was added.
Model wording, strategy, timing and optional CTA remain model-owned. Facts,
safety, intake budgets/recovery and terminal handoff remain deterministic.

The provider-neutral instructions live once in `agentic_surface_instructions`.
They teach understanding, trusted answering, useful next step and continuation
when useful. No new phrase IDs, forced commercial composition or CTA were added.
Anthropic and OpenAI eval share the same typed schema/instructions. Legacy Python
proposals remain readable; new strict provider schemas require explicit scopes
and advisory plan. Anthropic's output budget was not changed or live-tested.

### Phase 1.1 evaluation contract

Oracle v4 adds a noncritical `commercial/general_clarification` check for the
existing unresolved commercial fixtures. It observes retained question targets
plus broad meaning cues in the emitted text, not labels alone or exact canned
wording. Generic help/fallback fails this product check even if factual safety
passes. These finite cues can reject novel valid wording and are not a semantic
proof; human review decides product quality. Continuation presence is an
allowlisted diagnostic from retained purpose, never a required CTA or score.

Live record v9 keeps v2/v3 oracles and v8 records readable without applying v4
checks to history. Existing evidence/Customer review notes are frozen. No fixture,
model, output limit, deadline, pricing or latency gate changes accompany this
round. `--commercial-only` runs the three existing cases once on one US$0.30
ledger, stops on any failed check and never authorizes B. The separate ten-case
smoke retains its US$1 cap and critical stop rules; latency alone never aborts it.


### Phase 1.1 validation outcome

950 tests and all static checks passed; four independent reviews passed after
fixes for released-episode authority, generic-topic eval false positives and
undeclared recovery offers. The recovery veto recognizes a bounded invitation
cue; it does not choose wording or claim exhaustive semantic detection.

The [observed results](../evals/V1/agentic-phase11-results-2026-10-04.md) record
three passing commercial cases, then a fresh ten-case smoke stopped at case 5:
`live_incomplete_output`, valid usage, output 512 including reasoning. Four
complete replies passed; five cases were never executed. No retry or post-stop
configuration change was made. Direct price remains answer-only for human
review; no forced CTA hides this remaining product concern.

Functional safety passing != product conversational quality passing. The new
smoke is blocked, human review remains NOT YET APPROVED, and partial observed
p95 E2E fails 8s. Phase B is paused, Ticket 12 in-progress, ADR 0009 proposed.
Historical evidence and product-owner annotations are preserved, without rescore.

## Phase 1.2 — Commercial Initiative + Generation Headroom

The [approved amendment](../specs/V1-agentic-surface-phase-1.2.md) strengthens
`agentic_surface_instructions()` once for both provider paths. Commercial
initiative is soft policy: answer trusted information, assess a useful next step,
continue naturally when appropriate. A Customer seeking information only,
social conversation or safety context does not require sales continuation.
The existing advisory `continue_conversation` covers sales/qualification without
creating an action, intake or Appointment. CTA, timing and wording stay model-owned.
No renderer, factual/handoff/appointment authority or persistence changes.

Eval trace retains `next_action` and continuation presence. New
`conversation_closed_early` is a tri-state heuristic: true for a proposed
commercial Intent with answer-only planning and no retained continuation/question,
false when such a question/continuation remains, otherwise unknown. It does not
establish that the Customer wanted progression and can flag a legitimate
information-only answer. Human review interprets it; no oracle gate uses it.
Suppressed/failed/safety outcomes have no early-closure product judgement.

The prior smoke reached output 512 including reasoning 264 with `incomplete`,
valid usage and no timeout. This is consistent with headroom exhaustion, but its
unrecorded provider reason is not retroactively inferred. Diagnostics now capture
only allowlisted `incomplete_details.reason` (`max_output_tokens`, `content_filter`,
or `unrecognized`), presence and existing counters/status. Missing remains unknown;
no CoT, provider text/payload or arbitrary error string is retained.

`llm_decision.MAX_OUTPUT_TOKENS=1024` centralizes the authorized ceiling. Live
OpenAI request, budget reservation and config record use it, previously 512.
Anthropic runtime default/upper bound and `.env.example` use it, previously 200;
explicit lower configuration remains honored and local `.env` is untouched.
Anthropic thinking stays disabled and is not live-called. Output headroom is a
ceiling, not a target. Paid incomplete calls retain their actual cost and safe
system outcome, without inflating completed-model-reply denominators or retries.

Model, effort, tier, pricing, production 10s deadline, eval 30s observation budget,
and official 8s E2E gate remain unchanged. A bigger output ceiling may increase
cost/latency and does not guarantee completion. Hitting 1024 is recorded as a
headroom concern; another incomplete blocks the run without automatic escalation.
Finite prose/behavior recognition and the separate human approval gate remain.

### Phase 1.2 validation outcome

971 offline tests (21 added) and all checks passed; four independent reviews
approved. The [new evidence](../evals/V1/agentic-phase12-results-2026-10-04.md)
records 4/4 targeted and 10/10 smoke complete, valid model replies with no
incomplete/fallback/retry, 0/19 smoke critical failures. Price continued with
a free Customer-goal/style question in both runs; no fixed CTA was introduced.
Output max was 438 in retest and 462 in smoke, below the new ceiling.

Observed p95 E2E 12.523s (retest) and 10.812s (smoke) fail 8s. No diagnostic metric
approves that gate. Human product review and real-provider E2E remain pending;
Phase B paused, Ticket 12 in-progress, ADR 0009 proposed. The original incomplete
run is preserved without inferred reason or rescore. Review the ten-response
qualitative packet before product approval; no automatic ratings are assigned.
