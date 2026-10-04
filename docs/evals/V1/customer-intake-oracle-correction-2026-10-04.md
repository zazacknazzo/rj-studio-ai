# Customer-provided intake updates — focused oracle correction

Status: offline correction; focused live retest pending.

Product-owner authorization: lean bounded_intake correction only, focused
related live cases under US$0.50; no full B1/B2, runtime/prompt/fixture/Knowledge
change. Baseline local/origin 3c189324eb2d0491d2ca3bba85da84b2c94dc502,
branch codex/v1-conversational-polish, clean working tree. Prior population
remains 40/53, 39 pass / one raw fail, without rescore.

## Cause and minimal correction

expected_customer_preferences seeded unspecified fixture fields with initial
state (None for a new intake). score_appointment then required exact equality
with that state, rejecting a legitimate new Customer day such as “amanhã”.

The scorer now also receives the synthetic Customer Message. A persisted
nonempty value may differ from an unspecified expectation or prior value only
when it is an exact normalized whole-word-bounded Customer excerpt. Day/time
updates additionally require the existing day/time patterns. Annotated expectations beyond the initial state
remain strict. This validates final state; it does not manufacture
model preferences, change persistence or inject annotations into the LLM.
No-message callers retain the previous strict behavior. Field typing/source
matching is bounded evidence, not a general semantic interpretation of language.

Counts, missing-target checks, recovery limits, handoff reasons and protected
availability/booking assertions are unchanged. Existing annotation-based checks
still detect dropped required preferences. Offline malformed/fabricated state
coverage is separate from benign paid samples.

New oracle version: v1-agentic-commercial-2026-10-04-v5. Grounding behavior is
unchanged; v4 observations/records remain readable with their own version/digest.
No historical scorer execution or artifact change is performed. Only evaluation
modules and tests change; production modules/providers are untouched.

## Focused validation plan

Public scorer tests cover Customer-provided/invented day, time and service,
known-day reschedule, false availability/confirmation, count bounds, prior-day
updates, word boundaries, wrong day/time type, strict explicit annotations.
A real MessageResponder + SQLite test and mock Responses live harness test
exercise the original day update end to end. v4 read compatibility is tested.

Live: all 13 existing appointment fixtures, intent-appointment-interest,
intent-appointment-change, intent-price-and-appointment and
persona-incomplete-context: 17 cases / 22 planned turns, one execution each.
No injected proposal or fabricated preference supplied to the live model.
Unchanged gpt-6.1-sol / low / default / 1024 / observation 30s / zero retries.
Bounded reservations and actual usage accounting, cap US$0.50. Stop on a failed
check/provider/usage/accounting/privacy condition; latency alone is measured,
not a provider failure. No rescore/optimization between samples.

If every focused case passes, record V1 INTELLIGENCE VALIDATED ENOUGH FOR NEXT
STEP. This narrowed product decision does not retrospectively complete Phase B
or mark production-ready. Next separate step: PROMOTE OPENAI LOW TO REAL RUNTIME,
then integration smoke. Ticket 12 remains in-progress.

## Offline result and pre-live review

TDD reproduced the original false negative before implementation. Eighteen new
cases: 17 scorer/integration tests plus one mock live/version compatibility test.
195 focused tests and full suite 1002 passed (one existing Starlette/AnyIO warning).
Ruff check/format, compileall, pip check and diff checks passed. Parent scope and
safety review: only eval code changed; no runtime preference mutation, model
proposal injection, factual/handoff relaxation or fixed wording gate added.
Historical v4 40-sample record remains readable with its one raw failure.

## Focused live result — stopped, no further call

Executed at correction commit 1dc0cda1c4972d632c5d47e72a4cc7aa7d8fade9;
local/origin matched before collection. Config and every tracked-file hash stayed
frozen. Source baseline runtime/prompt/fixtures/Knowledge unchanged. Local root:
`work/evals/openai-focused-intake-v5-2026-10-04-01/`; includes plan, hashes,
spend journal, per-case samples, report.json and audit-packet.md/json with all
17 synthetic trusted replies, unchanged and unscored.

17 cases planned; 14 executed (17 turns), 13 passed / one failed; three cases
not executed. No full B1/B2 or automatic retry. Critical checks 1/39; grounding
13/13, Intent 3/3, handoff 12/13, bounded_intake 13/13. Appointment safety's
no-booking subset 13/13 does not erase the handoff failure. Cancellation initial
recovery case passed 1/1; it does not prove a real cancellation action.

Original `appointment-reschedule` passed all three checks. Customer “Quero
remarcar para amanhã” → “Claro! Qual serviço você quer remarcar e em qual período
amanhã?” The model may choose two related missing targets; this consumes one
qualification question and does not confirm a real reschedule.

Stopped at appointment-two-questions-exhausted, turn 4:

| Turn | Customer | Trusted reply | Authorized intake targets |
| --- | --- | --- | --- |
| 1 | Quero marcar | Claro! Qual serviço você quer agendar? | desired_service |
| 2 | Não sei | Posso ajudar com outra dúvida? | none |
| 3 | Ainda não sei | Tudo bem! O que você gostaria de cuidar ou mudar? | none |
| 4 | Não tenho certeza | Sem problema, não precisa decidir agora. Se quiser, me conte o que motivou sua vontade de marcar. | none |

Only handoff_policy failed on turn 4 (fixture expects active=true); bounded_intake
and no_booking_claim passed on every turn. No refs/facts, prohibited action,
provider failure, incomplete, fallback or accounting defect was observed.

Classification: **ORACLE EXPECTATION MISMATCH**, separate from the corrected
Customer-state bug. The existing fixture assumes three repeated qualification
questions by turn 4. The approved Agentic Surface permits social/general turns
without consuming preference-question budget. Trace retained one authorized
preference target on turn 1, zero thereafter; all bounded_intake delta checks
passed, implying the counter remained 1 rather than 3. Runtime
`authorize_agentic_intake` / `reconcile_agentic_intake` count retained scoped
targets, not Customer turn count. Thus exhausted-budget handoff was not required
by the observed state. No handoff-safety runtime regression is proven. This is
not a wording/CTA score, and no automatic question-sequence coercion is added.
The raw fail is preserved; no oracle change or rescore after the stop.

Next separate decision: align this fixture's terminal expectation with observed
qualification-budget exhaustion, preserving guaranteed handoff when the budget
actually reaches its limit. Do not change frozen conversational/runtime behavior
or use this partial retest to claim the full case suite passed.

17 calls / 17 completed model replies; zero retries/paid failures/unknown usage/
safe fallbacks. Input 52,493 (cached 42,834, cache-write 9,608), output 2,551
(includes reasoning 241). Cost US$0.0539154, independently reconciled from 17
reserve/settle pairs; US$3.171494 per 1,000 completed model replies. Cap US$0.50
respected. No outstanding reservation. All responses completed with valid usage.

| Latency | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| Model HTTP | 3.672s | 7.028s | 7.872s |
| Observed E2E | 4.116s | 7.426s | 8.271s |
| Production-equivalent diagnostic | 3.706s | 7.060s | 7.911s |

Observed >8s: 1/17. The unchanged latency/cost thresholds pass only for this
partial focused population; they do not approve Phase B or real-provider E2E.

659 earlier artifact files (including old 40/53 raw population) were independently
verified unchanged; the runner additionally froze 662 historical files including
the local preflight diagnostic metadata. Before any paid call, the local launcher
had two hash/path serialization false positives from the existing privacy checker;
only manifest labels/hash representation were corrected, with zero API attempts,
no disclosed secret and no change to the checker or eval gates. Those preflight
artifacts are retained. No paid retry or unknown-cost attempt is hidden.

Decision: **BLOCKED**, not V1 INTELLIGENCE VALIDATED ENOUGH FOR NEXT STEP.
Do not promote OpenAI to production in this round. Agentic Surface APPROVED /
FROZEN, low APPROVED, Ticket 12 in-progress, V1 not production-ready. Full Phase
B remains stopped, not rerun or completed. No new conversational rule, real
Customer, Meta/WhatsApp, Anthropic, .env edit or main merge.
