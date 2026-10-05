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

Minimal live plan, unchanged gpt-6.1-sol / low / default / 1024 / observation 30s:

- A: the existing four-turn appointment-two-questions-exhausted fixture, without
  forced decisions. Observe actual counters; no handoff for unconsumed budget.
- B: real exhaustion state, seeded by three deterministic authorized questions
  through the existing application/persistence/outbox seams, then one live answer.
- C: the immediately-below-limit prefix of the same existing scripted fixture,
  two real authorized questions seeded, then one live answer. The last permitted
  question can bring the count to 3 without premature handoff on that same reply.

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
Ticket 12 may remain in-progress. No real Customer, Meta/WhatsApp or Anthropic.

## Pre-live checks

TDD first failed only handoff_policy for an active one-question state despite
four turns. Minimal counter-based expectation made it pass. Twelve new public
scorer/runtime tests; focused 195 passed, full suite 1014 passed (one existing
Starlette/AnyIO warning). Ruff check/format, compileall, pip check and diff checks
passed. Parent scope review: changes restricted to eval metadata/scorer, this
fixture's expectation flag, tests and documentation; no runtime/prompt change.

## Live result and product decision

**V1 INTELLIGENCE VALIDATED ENOUGH.** All three authorized scenarios passed.
Further rounds of V1 intelligence eval are closed by this product-owner
conditional approval. No B1, B2 or 17-case rerun is authorized by this result.
Historical failed populations keep their original results; no rescore.

Runtime/scorer freeze commit: 281ed62. Configuration unchanged: gpt-6.1-sol,
low, default tier, output ceiling 1024, observation 30s, zero retries. No production
provider selection change; OpenAI remains eval-only. All tracked files kept
identical hashes throughout the paid population; 729 historical artifacts
unchanged. Only this result documentation updated after collection.

| Scenario | Observed intake count | Handoff | Result |
| --- | --- | --- | --- |
| A: existing four-turn fixture | 0→1→1→1→1 | inactive throughout | PASS |
| B: actual exhausted budget | seeded 3→3 | active, appointment_intake_limit | PASS |
| C: immediately below limit | seeded 2→2 | inactive | PASS |

B/C history was created by deterministic authorized questions through real
MessageResponder + SQLite, not by setting counters directly. Paid generation
was real OpenAI; outbound acceptance was fake only. A contains four fresh
paid turns; B/C each one. Below-limit general questions did not charge intake
budget; the real exhausted case created terminal handoff. No forced wording or
model proposal in paid turns. No false booking/availability or invalid reason.
Grounding/no-booking 6/6, handoff 6/6, bounded intake 6/6, critical 0/18.

Six calls / six completed model replies, zero retries/paid failures/unknown
usage/safe fallbacks. All responses completed with valid usage. Six budget
reservations settled; independent Decimal reconciliation matched US$0.0418503.
US$6.97505 per 1,000 completed model replies; cap US$0.15 respected.
Input 18,889 (cached 6,118, cache-write 12,753), output 932 including reasoning 59.
The offline launcher mock used synthetic credentials/MockTransport, no external
call, and temporary artifacts; its samples/cost are excluded from live metrics.

| Latency | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| Model HTTP | 4.547s | 8.731s | 9.324s |
| Observed eval E2E | 5.300s | 9.207s | 9.835s |
| Production-equivalent diagnostic | 4.580s | 8.763s | 9.356s |

Observed E2E >8s:1/6. **The unchanged official 8s latency gate fails in this
small population.** No threshold waiver, diagnostic substitution or production
readiness is claimed. This closing decision follows the explicitly narrowed
intelligence/state/safety criteria; it does not complete all original Ticket 12
operational gates. Real runtime latency/10s deadline compatibility and real
provider integration remain work for the separately approved promotion/smoke.
No additional intelligence run or optimization is started to address this sample.

Local evidence: `work/evals/openai-exhaustion-v6-2026-10-05-01/`, including
plan, frozen hashes, per-scenario LiveRecords, intake-counts.json,
trusted-responses.json, spend.jsonl, report.json and audit-packet.md/json. No
CoT/full provider payload, secret or real Customer data retained. No automatic
naturalness scores. Six observed replies, unchanged:

| Scenario/turn | Customer | Trusted reply |
| --- | --- | --- |
| A1 | Quero marcar | Claro! Qual serviço você quer agendar? |
| A2 | Não sei | Tudo bem! O que você gostaria de cuidar ou mudar no seu visual? |
| A3 | Ainda não sei | Sem problema, não precisa decidir agora. Podemos começar pelo que te incomoda ou deixar para quando você tiver uma ideia. |
| A4 | Não tenho certeza | Tudo bem, sem pressa. Quando quiser retomar, estou por aqui para te ajudar. |
| B | Não tenho certeza | Perfeito. Vou passar sua preferência à equipe para confirmar a disponibilidade. |
| C | Ainda não sei | Tudo bem, não precisa ter decidido. O que você gostaria de cuidar ou mudar no seu visual? |

Next mandatory separate round: **PROMOTE OPENAI LOW TO REAL RUNTIME**, then
integration smoke. Agentic Surface APPROVED/FROZEN, low APPROVED, oracle corrected
v6, V1 intelligence validated enough. Ticket 12 in-progress pending runtime and
operational gates; V1 not production-ready. No runtime, prompt or conversational
rule change; no Meta/WhatsApp, Anthropic, real Customer, .env edit or main merge.
