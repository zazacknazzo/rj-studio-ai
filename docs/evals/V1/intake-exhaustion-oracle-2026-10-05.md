# Intake exhaustion oracle — minimal closing gate

Status: offline correction; live gate pending.

Product owner authorized only correction of the terminal handoff expectation
for appointment-two-questions-exhausted, offline checks and 2–3 live scenarios,
US$0.15 cap, no retry. Baseline codex/v1-conversational-polish, local/origin
matched e3b8a0170013ab382b29b19e5b9fc411b8503bed, clean working tree.
No main merge, full B1/B2 or 17-case rerun. Historical raw failures remain intact.

## Minimal change and unchanged limits

Previous live expectation assumed terminal handoff on turn 4 regardless of
actual committed intake questions. Customer turn count is not intake budget.
A scoped fixture flag now makes handoff depend on persisted prior
clarification_count >=3. The third permitted question may consume the last unit;
its following Customer answer receives existing terminal policy. Below the
limit, this exhaustion-only scenario does not require handoff. No runtime
threshold or handoff authorization changed.

Budget/delta checks still reject count >3, asking beyond the limit and charging
more than one unit for one committed question. Known-field questions remain
invalid; wrong/missing terminal handoff fails. Social, approved factual answers
and general non-intake questions do not consume the scoped intake budget.

Only this fixture receives the flag. Its old count/contains annotations remain
for the existing deterministic legacy scripted sequence, which actually asks
three questions. They do not become a live question/wording obligation. Metadata
never enters a model prompt. Other fixtures retain their handoff policies.
Oracle version v1-agentic-commercial-2026-10-05-v6 identifies this change;
v4/v5 evidence remains readable, not rescored. Grounding behavior unchanged.

## Offline/live seams

Test public score_appointment and actual MessageResponder + SQLite: one question
across four turns; real exhaustion; last allowed question; overrun; repeated
known field; wrong/premature handoff; multi-target single charge. Social/factual/
general question behavior is exercised through the unchanged runtime, not only
numeric mock state. Existing handoff/intake/grounding regressions remain required.

Minimal live plan, unchanged gpt-6.1-sol / low / default / 1024 / observation30s:

- A: the existing four-turn appointment-two-questions-exhausted fixture, without
  forced decisions. Observe actual counters; no handoff for unconsumed budget.
- B: real exhaustion state, seeded by three deterministic authorized questions
  through the existing application/persistence/outbox seams, then one live answer.
- C: the immediately-below-limit prefix of the same existing scripted fixture,
  two real authorized questions seeded, then one live answer. The last permitted
  question can bring the count to3 without premature handoff on that same reply.

B/C setup is explicitly synthetic deterministic history, outside paid/E2E samples;
no model output for a paid turn is injected. Test-only orchestration observes
only counts, authorized targets and handoff state/reason from ephemeral SQLite.
No general-purpose seed framework or runtime API is added. All responses/counts,
usage, costs and latency retained; cap US$0.15, zero retries, stop on failed checks
or unknown billing/provider/privacy. Latency alone measured separately.

Only all passing scenarios authorize the explicit product decision
V1 INTELLIGENCE VALIDATED ENOUGH and closure of further V1 intelligence eval
rounds. This does not declare historical Phase B complete or production-ready.
Next separate step: PROMOTE OPENAI LOW TO REAL RUNTIME, then integration smoke.
Ticket12 may remain in-progress. No real Customer, Meta/WhatsApp or Anthropic.

## Pre-live checks

TDD first failed only handoff_policy for an active one-question state despite
four turns. Minimal counter-based expectation made it pass. Twelve new public
scorer/runtime tests; focused 195 passed, full suite 1014 passed (one existing
Starlette/AnyIO warning). Ruff check/format, compileall, pip check and diff checks
passed. Parent scope review: changes restricted to eval metadata/scorer, this
fixture's expectation flag, tests and documentation; no runtime/prompt change.
