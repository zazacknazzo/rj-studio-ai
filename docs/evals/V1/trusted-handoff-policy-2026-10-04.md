# Trusted Handoff Policy Gate — 2026-10-04

Approved runtime correction on `codex/v1-conversational-polish`, baseline
`b76e7febe0484edaf31050ed7d6d476afc6b9274` (published before edits).

## Cause and scope

REAL_RUNTIME_BUG: `finalize_reply` treated `decision.handoff=true` as sufficient
to call `_clarify`; MessageResponder normalized its reason and atomically
persisted a new episode. A valid release was not lost. Sanitization never
proved need. The new explicit gate denies model-only proposals, changing only
handoff/reason fields; existing trusted branches authorize their own reasons.
The same Reply AST is then rendered and validated normally. ADR 0008 records
the policy and the separately scoped model-Intent/recognition limits.

History, release, persistence, appointments/cancellation, Knowledge, prompts,
providers, oracle v2, scoring, model/pricing/output/timeouts are unchanged.
The prior oracle-v2 B1 stays at 50/53, 49 pass / one fail, B2 absent; its added
validity sidecar excludes it from the final gate due to the runtime change.

## Pre-paid validation

TDD first reproduced benign greeting + model handoff, without history/release.
Deterministic integration coverage exercises greeting/OTHER, preserved plans,
release + restart + replay + history, mandatory current risk/human/complaint/
legal/payment despite model=false, approved Knowledge conditions and bad refs.
Existing appointment/cancellation, active suppression and concurrency regressions
remain required. 31 new parametrized tests; full suite **831 passed**, focused
handoff/grounding/appointment/polish/trace checks **228 passed**. Ruff check/
format, compileall, pip check and diff checks passed. One existing Starlette/
AnyIO deprecation warning remains. Three independent reviews precede paid retest.

## Live gates

Isolated retest: prior handoff and suppression seeded deterministically, explicit
manual release and restart, then one live generation for “Oi”, US$0.20 cap.
If passed, a fresh 53-case B1 and conditional approved B2 share one US$5 ledger.
No historical samples enter new counts. Config remains gpt-6.1-sol / medium /
default / output 512 / observation 30s / zero retries. Product latency remains
observed billable p95 <=8s; diagnostic timing cannot replace it. Synthetic
Messages, isolated SQLite, fake Provider Acceptance only.

## Independent pre-paid reviews

All reviewed `b76e7fe...75fde4f`, independently, read-only:

- Product/spec: APPROVE, zero material omissions, scope creep or implementation
  findings. Revised model-only test expectations match the approved contract;
  trusted risk/Intent/Knowledge/appointment/cancellation coverage remains.
- Safety/handoff: APPROVE, zero material findings. Independently passed 248
  focused tests, 40 assertions across all familiar reason codes (benign plans
  denied, missing plans fail closed), and a pending-delivery/fake-acceptance/
  release/restart/replay scenario with terminal suppression preserved.
- Standards: APPROVE, zero documented violations or material design smells.
  Small typed gate at the existing finalizer seam, no new orchestration layer.

No paid call preceded these verdicts. Prior oracle review count clarification:
its fixture contained 13 grounding cases, not the reviewer’s original printed
14; all loaded cases were actually compared. Original records are unchanged.

## Isolated live retest

Frozen revision `d93e4dc84059ac04f146ee4c787b1f0e9a6e8d2b`. Prior human request
and suppressed inbound were seeded through the real runtime with a deterministic
fake, then fake-accepted, manually released and reopened. The single paid turn
was “Oi”: proposed Intent greeting, model handoff **true**, trusted authorization
**false**, persisted episode inactive, trusted reply **“Oi!”**, no fallback.
The retained history contains the prior request, confirmation and suppressed
Message. No history or suppressed processing was erased/revived.

One complete response with validated usage, zero retries/paid failures; input
1,920 (cache-write 1,917), output 148 including 70 reasoning tokens. Estimated
cost **US$0.0062785**, cap US$0.20, peak reservation US$0.01248. Model latency
4,633.70ms; observed E2E 5,800.27ms; diagnostic equivalent 4,659.39ms.
Handoff checks 2/2, critical 0/2; this diagnostic is excluded from fresh B1.

Private evidence: `work/evals/openai-trusted-handoff-retest-2026-10-04-01/`.
After saving the actual sample and settled journal, the private export wrapper
rejected an allowed request digest using an over-broad privacy check and exited.
The original script/sample/journal remain unchanged. Offline reporting recovery
used their actual usage/checks and matched the trusted catalog rendering to the
saved reply hash; no response edit or second call. No request digest was invented:
the full envelope/digests remain unavailable. A separate independent read-only
product/spec check verified sample schema, usage/journal, summary, privacy and
exact reply hash, and approved this case PASS for conditional B1. This limitation
is explicit; no provider/privacy/accounting defect or additional call occurred.

## Fresh B1 — stopped at case 32

New root: `work/evals/openai-phase-b-trusted-handoff-2026-10-04-01/`.
All 53 cases were planned from case 1, no resume/reuse of old records. B2 planned
35 probabilistic cases twice more (70 executions / 90 turns), only after every
B1 check passed, and sharing the same US$5 ledger. Model/effort/output/deadline
and oracle v2 were unchanged. All **194 tracked-file hashes** stayed frozen.

Stopped immediately on `critical_failure` at case 32,
`grounding-mandatory-policy`: **32/53 executed, 31 pass / one fail**.
21 cases not reached. **B2 not executed**: zero calls and zero repetitions.
The 316 pre-existing evidence files are byte-for-byte unchanged; the old B1
remains 50/53, 49 pass / one fail and invalid for the final gate after runtime fix.
No subsequent paid call, runtime/prompt/oracle edit or retrospective rescore.

### Exact failure evidence

Synthetic Customer: “Quero corte com desconto.” Selected facts:
`service-corte`, `policy-corte`. Model proposed promotion_or_discount +
appointment_interest, declared/rendered `policy-corte`, handoff false. Finalizer
handoff false, persisted handoff inactive, no fallback or rejected references.
Actual persisted reply: “Não há desconto autorizado para corte. Qual dia seria
melhor pra você?” `handoff_policy` PASS; `trusted_facts` FAIL.

Read-only replay confirms reference validity, required-policy inclusion, no
excluded claim and factual relevance all pass. The only failing predicate is
nonempty residue **“Qual dia seria melhor pra você?”** after the oracle removes
approved facts, persona phrases and handoff confirmations. That exact question
is the existing deterministic `appointment_intake.intake_question` for
`preferred_day`, appended by MessageResponder after trusted fact rendering.
The oracle allowlist omits intake questions when grounding and intake coexist.
An independent read-only safety review reproduced the same failed predicate
and confirmed this classification, with intake/application/oracle hashes
matching the frozen population. No source edit or network call occurred.

Classification: **HARNESS_BUG — missing permitted deterministic intake surface**,
not evidence of invented discount, fact or availability, or renewed handoff.
The raw failure remains **1/21**, not waived or silently reclassified into PASS.
The approved scope explicitly forbids oracle/scorer edits here. A separately
approved correction should validate the actual persisted intake state/question
provenance and add grounding+intake coverage, not allow arbitrary question text.

### Quality — fresh B1 only

| Metric | Result |
|---|---:|
| Cases executed / planned | 32/53 |
| Case pass / fail | 31/1 |
| Critical failed checks / evaluated critical checks | 1/21 |
| Grounding | 11/12 |
| Intent | 15/15 |
| Handoff | 9/9 |
| Appointment safety | 0/0 (its cases not reached) |
| Persona surface evaluable / pass / fail / not-evaluable | 6/6/0/0 |

These are checks, not counts of unsafe customer replies. Surface checks are
not human naturalness scores; qualitative product approval remains recorded.

### Cost — all 32 billable attempts

| Metric | Result |
|---|---:|
| Calls / retries / paid failures | 32/0/0 |
| Valid completed model replies / local safe fallbacks | 32/0 |
| Input tokens | 60,846 |
| Cached / cache-write / ordinary input | 50,778 / 9,972 / 96 |
| Output tokens | 4,750 |
| Reasoning tokens (already included in output) | 1,751 |
| Versioned estimated cost | US$0.0776998 |
| Cost / 1000 completed model replies | US$2.42811875 |
| Peak spend including reservation | US$0.0823213 |
| Shared B1/B2 cap | US$5 |

32 journal settlements match 32 recorded attempts with validated usage, no
unknown cost or outstanding reservation. The failed semantic case is still a
completed valid model reply and stays in cost/latency. This session: 33 paid
calls including the separate retest; total estimated cost **US$0.0839783**.
No mixing historical or retest samples into B1 denominators.

### Latency — 32 billable executions

| Metric (ms) | p50 | p95 | Max | >8s |
|---|---:|---:|---:|---:|
| Model request | 4075.91 | 7166.68 | 7411.84 | 0/32 |
| Observed eval E2E (official) | 4545.01 | 7583.69 | 7833.38 | 0/32 |
| Production-equivalent diagnostic | 4101.58 | 7197.07 | 7438.43 | 0/32 |
| Eval-only input count | 372.02 | 635.42 | 845.89 | 0/32 |

All timing components are present. Diagnostic timing never replaces the
unchanged official 8s gate. Model time dominates; real WhatsApp E2E is untested.

## Gate outcome and remaining blockers

- Trusted-handoff correction and isolated retest: PASS.
- New final semantic gate: **FAIL / incomplete**, case 32 oracle finding.
- Cost and official latency: partial-population measured PASS; no overall V1
  approval, no B2, no new model winner.
- Follow-up requires explicit approval to correct the identified oracle seam
  and choose a new population; this task makes no scorer change.
- Separate Intent/recognition trust limitations remain documented in ADR 0008.
- Meta/WhatsApp real E2E remains pending; Anthropic comparison deferred.
- Ticket 12 remains **in-progress**.

No secrets, real Customers, Anthropic, Meta/WhatsApp messages, real appointments,
main merge, history deletion, fabricated references or guardrail relaxation.
All new report/raw artifacts remain private and ignored; only concise sanitized
docs/code/tests are committed.
