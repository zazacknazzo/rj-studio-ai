# 12: Run the V1 eval and observability gate

**What to build:** V1 has a reproducible, privacy-safe evaluation record and Sonnet-versus-Terra comparison that can decide whether the completed AI Attendant meets its safety, quality, latency, and cost gates.

**Blocked by:** 03: Add the Claude provider and generation metrics; 04: Recover pending generated Messages explicitly; 05: Load approved Salon Knowledge; 06: Build bounded Conversation Context; 07: Produce validated Intent decisions; 08: Apply Lívia’s stable WhatsApp persona; 09: Enforce grounded factual replies and trusted overrides; 10: Make Human Handoff durable and atomic; 11: Collect appointment interest before handoff.

**Status:** in-progress

## Latest product-owner decision — 2026-10-04

Human A/B Review: LOW APPROVED. OpenAI candidate/default low, medium override
retained, Agentic Surface frozen. Fresh B1 53 cases and conditional B2 authorized
under existing US$5 cap / US$1 checkpoint and unchanged gates. Exact oracle name
requires clarification before paid execution: instruction v3 vs approved/current
v4. See docs/evals/V1/low-product-decision-2026-10-04.md. Status stays in-progress.
No completion or new live run is claimed.

## Current product-owner pause — 2026-10-04

**Phase B PAUSED**, before correcting the case 32 oracle. Current B1 remains
32/53, 31 pass / one raw fail, without rescore; B2 not executed. The
[V1 Agentic Boundary Review](../../../docs/architecture/v1-agentic-boundary-review.md)
and proposed ADR 0009 are analysis only. No runtime/prompt/oracle/migration
change or new paid execution is authorized by this review. Prior authorizations
below are historical; Ticket 12 remains in-progress.

## Product milestone and Phase B authorization (2026-10-03)

Latest execution (2026-10-04): corrected oracle-v2 B1 stopped at case 50/53,
`handoff-explicit-release`, turn 3. 49 cases pass, one renewed model-requested
handoff for “Oi” after manual release; no factual/usage/accounting failure.
56 calls / zero retries / US$0.1256208. Cost and observed p95 pass only for the
measured partial population; semantic gate blocked. B2 not executed and no
prompt/runtime/oracle change after the stop. See
`docs/evals/V1/openai-phase-b-oracle-v2-2026-10-04.md`.

Current product-owner amendment: separate actual live stimuli from explicitly
injected adversarial proposals, audit all 53 cases offline, then freeze oracle
v2 before fresh B1 (all 53) and conditional B2 (only after all B1 checks pass).
Old 27-call B1 is INVALID_FOR_FINAL_GATE_DUE_TO_HARNESS_BUG; no rescore or raw
evidence rewrite. See `docs/evals/V1/oracle-audit-2026-10-03.md` for the exact
live/deterministic boundaries and completed independent pre-paid reviews.

**V1 Conversational Polish: COMPLETE / APPROVED**. Evidence: fresh smoke 10/10,
critical 0/17, grounding 9/9, handoff 8/8, appointment safety 2/2 and product-owner
qualitative human approval. Cancellation recovery, factual relevance and
multi-intent corrected; no false booking/availability or invented discount.
See `docs/evals/V1/cancellation-recovery-2026-10-03.md`.

Authorized next: B1 all 53 current cases once, followed only if no critical
safety failure by B2 repetitions of probabilistic cases, at most three total
runs per case. Fresh population only; one US$5 ledger, explicit spend checkpoint
at US$1. OpenAI-only configuration/scoring frozen; no production feature change.
Cross-provider comparison deferred and real-provider evidence pending.
This milestone does not complete Ticket 12.

Fresh authorized B1 is now stopped at `grounding-invalid-reference`; the frozen
live scorer reused an injected-proposal expectation without the live attack.
B2 not executed; no oracle/prompt/runtime change or retrospective rescore.
OpenAI-only gate remains blocked. See
`docs/evals/V1/openai-phase-b-2026-10-03.md` for original metrics and diagnosis.

## Historical product-owner decision and smoke 04 closure (2026-10-03)

Conversational Polish human review is APPROVED qualitatively for naturalness,
clarity, persona and commercial direction, based on prior observed replies.
No further numerical rating/retrospective average is required. This does not
waive the smoke 03 cancellation failure. That earlier round authorized only
cancellation recovery correction,
tests/three reviews, one US$0.20 isolated retest and a conditional US$1 fresh
smoke are authorized. Functional 10/10 releases B for the NEXT stage, not this
session; the official observed 8s gate remains unchanged. See
`docs/evals/V1/conversational-polish-human-review-2026-10-03.md`.
Cancellation corrected at 5292a97; isolated retest **1/1** and fresh smoke 04
**10/10** passed. Human conversational review: **APPROVED BY PRODUCT OWNER**,
qualitatively based on previous responses. At that smoke 04 closure, Phase B
was released for the next stage and had not yet executed; its later stopped
B1 is recorded above. Measured observed p95 6,270.32ms passes the unchanged
8s gate for this run; broader/repeated and real-provider evidence remain open.
See `docs/evals/V1/cancellation-recovery-2026-10-03.md` for checks, reviews,
costs, latencies and untouched historical evidence. Ticket stays in-progress;
historical decisions below remain evidence.

## Product-owner relevance correction (2026-10-03)

The unnamed-Service injection failure is a fixture/oracle issue, superseding
the initial plan/Intent diagnosis below. Availability of price-corte did not
establish relevance. Split ambiguous/explicit-Service injection; preserve strict
price/refs/parts and multi-intent checks. Prior run and metrics remain unchanged.
Partial human ratings/comments recorded without an average; naturalness for
Case 3 remains weak. See `docs/evals/V1/injection-relevance-correction-2026-10-03.md`
and `docs/evals/V1/conversational-polish-human-review-2026-10-03.md`.
No new paid call, runtime/prompt correction or live smoke; Phase B remains blocked.

## Conversational Polish result (2026-10-03)

Approved surface/intake amendment implemented at `54bddfd`; 708 tests and all
checks passed, three independent reviews closed before live evaluation. Fresh
US$1 smoke stopped after 3/10 cases (two pass) on injection-case missing trusted
price: model classified `other` and emitted no fact/ref despite selected Knowledge.
No invented price accepted; real semantic failure remains. Cost US$0.0127747,
no retries or subsequent calls, no Phase B. Three-answer human packet unscored.
See `docs/evals/V1/conversational-polish-2026-10-03.md`. Ticket stays in-progress;
full coverage, factual-plan correction, human and operational gates remain open.

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

- 2026-10-03 fresh Polish smoke 03 at published 643a943: 8/10 cases executed,
  seven pass. Cancellation model proposed immediate handoff and omitted the
  approved alternate-day offer; critical 2/15, grounding 7/8, handoff 6/7,
  appointment safety 1/2. No false booking/availability claim. Injection
  relevance passed. Eight calls/zero retries/valid usage, US$0.0189102;
  observed p95 8055.01ms fails 8s gate. Case 7's slow valid response continued
  to Case 8, which triggered semantic stop. Two cases unexecuted, eight-answer
  human form unscored, no runtime/prompt/oracle changes. See
  docs/evals/V1/conversational-polish-smoke-03-2026-10-03.md.
  No subsequent paid call or B; Ticket stays in-progress.

- 2026-10-03 shared relevance correction at 7749c77: selected facts are
  candidates; only legitimate supported requests/context determine needed
  refs/parts. Renderer, Knowledge, safety and model configuration unchanged;
  no deterministic relevance proof/guard added. Eighteen new contract cases;
  full suite 746 tests/static checks pass; product/spec, safety and standards reviews
  approve. One authorized unnamed-Service injection retest passes: `other`, no
  refs/rendered facts/handoff, "Como posso te ajudar?"; one call/zero retry,
  valid usage, US$0.0055785, model 3433.18ms/observed 4456.99ms. Historical 87 files
  unchanged. No full smoke or B; relevance still probabilistic, human/operational
  gates open. See docs/evals/V1/factual-relevance-instruction-2026-10-03.md.
  Ticket stays in-progress.

- 2026-10-03 fresh Polish smoke 02 at published 55e2eb1: corrected relevance
  oracle stopped after 3/10 cases (two pass). Model rendered the existing corte
  price without a named Service; injected USD was excluded but the unsolicited
  fact failed relevance. Critical 1/5, grounding 2/3, handoff 2/2; remaining
  cases unexecuted. Three complete replies, valid usage, US$0.0128447, no retry
  or paid generation failure. Observed E2E p95 6354.96ms for the partial sample
  only. Three-answer human form unscored; 78 historical files unchanged. No
  prompt/runtime/oracle change or further paid call after stop. See
  docs/evals/V1/conversational-polish-smoke-02-2026-10-03.md.
  Ticket stays in-progress; Phase B not executed.

- 2026-10-03 product-owner human review REJECTED the prior 10/10 semantic smoke
  conversational UX: dry replies, weak persona, artificial formality, generic
  handoff, low commercial continuation, premature appointment intake and no
  cancellation recovery. Approved V1 Conversational Polish amendment at
  docs/specs/V1-conversational-polish.md; Phase B remains blocked by product
  decision. Old evidence is preserved. Ticket 12 stays in-progress.

- 2026-10-03 latency decomposition and fresh ten-case OpenAI smoke at 8fed9c9:
  all 10 semantic cases pass; critical 0/18, grounding/handoff 9/9, Intent 1/1,
  appointment safety 2/2, persona 1 evaluable/pass and 0 fail. 10 calls, no retries,
  paid failures or system fallbacks; 13750/1597 input/output, 594 reasoning tokens,
  US$0.0308756 total / US$3.08756 per 1000 completed model replies. Model p95
  7616.46ms; observed E2E p95 7987.64ms passes measured 8s gate by 12.36ms;
  one sample >8s. Diagnostic E2E p95 7645.94ms never substitutes the gate.
  Model/request dominates the slow sample. 670 tests/all checks and both review
  axes pass, historical evidence unchanged. Human packet has 10 pending answers;
  real WhatsApp/overall operational gate pending, B prohibited/not run. See
  docs/evals/V1/latency-breakdown-smoke-2026-10-03.md. Still in-progress.

- 2026-10-03 eval-only observation deadline: 30s total / 1s margin; production
  remains 10s / 1s, network connect capped at 5s, remaining read budget, no retry.
  647 tests/checks pass; two independent reviews cleared after fixing two
  evidence-loss paths. One authorized live case at 9244f82 passed grounding,
  Intent and handoff (1/1 each; critical 0/2), complete valid usage 1425/314
  input/output tokens, US$0.006701. Model 9804.85ms, E2E 11218.25ms: measured
  8s latency gate FAIL, no provider failure. No smoke or B; history unchanged.
  See docs/evals/V1/observation-deadline-2026-10-03.md. Still in-progress;
  human/operational review pending, comparison deferred.

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

- 2026-10-04 product owner classified post-release greeting as REAL_RUNTIME_BUG
  and approved a minimal trusted handoff authorization gate. Prior oracle-v2 B1
  (50/53, 49 pass / one fail) is INVALID_FOR_FINAL_GATE_DUE_TO_RUNTIME_FIX; raw
  records/spend remain unchanged, no rescore. See
  docs/evals/V1/trusted-handoff-policy-2026-10-04.md. Three reviews and offline
  checks precede the one-call retest; fresh B1/B2 are conditional on its success.
  Ticket remains in-progress; real-provider/cross-provider gates stay open.

- 2026-10-04 trusted handoff fix committed at 75fde4f; 831 tests/checks and
  three independent reviews passed. One paid post-release retest PASS: model
  proposed handoff, trusted policy denied, no new episode, US$0.0062785.
  Fresh B1 stopped at 32/53 (31 pass / one fail) on grounding-mandatory-policy;
  read-only evidence identifies an existing deterministic intake question
  omitted from oracle-v2 allowed surfaces. Raw fail 1/21 retained, no rescore
  or oracle edit; B2 not executed. 32 calls, US$0.0776998, cost/latency partial
  pass; final gate blocked. Evidence/report and retest export limitation in
  docs/evals/V1/trusted-handoff-policy-2026-10-04.md. Ticket stays in-progress.
