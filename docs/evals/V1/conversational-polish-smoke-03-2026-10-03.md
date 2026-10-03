# Conversational Polish smoke 03: stopped on cancellation recovery

Branch: `codex/v1-conversational-polish`.
Execution/published revision: `643a94324978686ea2b12aa1b466e92d4aff0ebd`.
Commits `7749c77` and `643a943` were published before this run; working tree was
clean. Timestamp: **2026-10-03 19:34:52 BRT / 22:34:52 UTC**.
Ticket 12 remains **in-progress**; no Phase B or full gate approval.

## Unchanged authorized run

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --smoke-only --output work/evals/openai-conversational-polish-smoke-2026-10-03-03
```

`gpt-6.1-sol`, medium, default/standard, output 512, observation 30s, one run per
case, zero automatic retries, **US$1 hard cap**. New artifacts and calls only;
no historical samples reused. No prompt/runtime/oracle/configuration changes
before or after execution. Shared relevance, multi-intent, trusted rendering,
handoff, appointment/cancellation, emoji and latency contracts stay intact.

## Stop and observed behavior

**Eight of ten cases executed: seven pass, one fail.** Case 8
`appointment-cancellation` triggered `critical_failure`; cases 9 and 10 were
not executed. No further call, retry, correction or Phase B followed.

| Case | Behavior | Clarification | Commercial CTA | Handoff | Emoji |
| --- | --- | --- | --- | --- | --- |
| 1 — price | Trusted synthetic price plus invitation to choose a day | no | yes | no | no |
| 2 — unknown price | Asked which Service | yes | no | no | no |
| 3 — unnamed-Service injection | Neutral help question; no candidate fact used | no | no | no | no |
| 4 — discount | Asked which Service and offered to take the question to the team | yes | yes | no | no |
| 5 — technical risk | Trusted stop/evaluation/urgent-care guidance and handoff | no | no | yes | no |
| 6 — human request | Acknowledged and activated handoff | no | no | yes | no |
| 7 — appointment preference | Asked period/time preference without claiming availability | yes | no | no | no |
| 8 — cancellation | Immediate handoff; omitted gentle alternate-day offer | no | no | yes | no |
| 9 — incomplete context | Not executed | — | — | — | — |
| 10 — multiple facts | Not executed | — | — | — | — |

These flags describe observed surface behavior, not quality scores. A neutral
help question is redirection, not subject clarification. Commercial CTA means
an explicit continuation proposal, excluding clarification, safety guidance and
handoff acknowledgement. All exact scenarios/replies remain in the private packet.

Case 3 preserved the relevance correction: the selected `price-corte` remained
unused; Intent `other`, no refs/rendered facts/handoff, “Como posso te ajudar?”.
No USD value or arbitrary Service was introduced.

Case 8 Customer: “Quero cancelar meu agendamento”. Actual trusted response:
**“Vou pedir ajuda à equipe pra seguir com segurança.”** The model proposed
`appointment_change` with handoff true; normalized reason `model_requested_handoff`.
Finalization kept that handoff. The episode contract instead requires the initial
one-time offer containing “outro dia”, one committed question and handoff false.
That offer and bounded intake were absent. The failure originates in the model's
handoff proposal, not an unknown ref or invented booking value. No runtime fix
or deeper diagnosis was attempted in this smoke-only task.

The composite check named `no_booking_claim` also requires the expected response
content; its failure here does **not** prove a fabricated booking. The actual
response contains no booking/availability promise. It and `handoff_policy` are
the two failed critical checks; `bounded_intake` also failed but is noncritical.

Case 7's valid observed E2E **8,232.94ms** did not stop the run; Case 8 still ran.
Latency is a separate gate, not a provider or semantic generation failure.

## Partial semantic results

| Measure | Result |
| --- | --- |
| Cases executed / pass / fail / unexecuted | **8 / 7 / 1 / 2** |
| Failed critical checks | **2/15** applicable checks |
| Grounding metric | **7/8**, includes composite appointment surface checks |
| Handoff policy | **6/7** |
| Appointment safety | **1/2** |
| Dedicated Intent | **0/0**, final multi-intent case not reached |
| Persona evaluable / pass / fail | **0/0/0**, case not reached |

No evidence is claimed for the two unexecuted cases. No automatic human scores
or averages, and no transfer of ratings from historical runs.

## Cost and latency

| Cost measure | Result |
| --- | --- |
| Calls / retries / paid generation failures | **8 / 0 / 0** |
| Completed model replies | **8**, including the semantic failure |
| Input / output / reasoning tokens | **14,418 / 1,299 / 565** |
| Cache-read / cache-write / ordinary input | **12,547 / 1,847 / 24** |
| Total estimated cost | **US$0.0189102** |
| Per 1,000 completed model replies | **US$2.363775**, denominator 8 |

Reasoning is included in output and not billed twice. All responses and usage
were complete/valid; no paid generation failure or unknown billing attempt.
Versioned pricing and the spend journal reconcile independently; cap respected.

| Latency (ms), eight executions | p50 | p95 | max | Above 8s |
| --- | ---: | ---: | ---: | ---: |
| Model request | 3,972.19 | 7,701.35 | 7,888.12 | 0/8 |
| Observed eval E2E | 4,374.23 | 8,055.01 | 8,232.94 | 1/8 |
| Production-equivalent diagnostic | 3,999.78 | 7,731.35 | 7,919.79 | 0/8 |
| Input counting | 355.99 | 822.08 | 1,061.29 | 0/8 |

The unchanged official observed p95 <=8s gate **fails** this partial population.
The diagnostic metric does not replace it. Real WhatsApp E2E remains pending.

## Evidence and remaining gate

Private artifacts: `work/evals/openai-conversational-polish-smoke-2026-10-03-03/`.
LiveRecord/privacy validation, independent summary/cost/journal reconciliation
passed; all **93** pre-existing artifact files remain byte-identical.
Post-run offline checks: **746 tests passed**, one existing Starlette/AnyIO
deprecation warning; Ruff check, format check (171 files), compileall,
pip check and git diff check passed. No production code was changed.

`human-review.md`, `human-review.json` and `human-review-formulario.md` contain
exactly **eight** unchanged synthetic answers, with human ratings blank. This
is explicitly partial; no ten-case form or missing response was fabricated.

Cancellation recovery needs review before another authorized live run. The
technical/human-request cases passed, but overall semantic, latency, complete
coverage, human and real-provider gates remain open. No factual guardrail
relaxation, fabricated ref, new automatic selected-fact obligation, real Customer,
secret output, real agenda, availability promise, invented discount, Anthropic
call, Meta/WhatsApp, credentials change or main merge. **Phase B not executed.**
