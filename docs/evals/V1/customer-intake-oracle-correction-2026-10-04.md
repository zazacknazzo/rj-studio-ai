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
