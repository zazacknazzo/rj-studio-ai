# Cancellation recovery: isolated retest and fresh smoke 04

Branch: `codex/v1-conversational-polish`.
Published evidence baseline: `a2d1c289bb1e63151d56df3458f40ff3e80e451a`;
working tree clean before that push, no main merge.
Execution revision: `5292a9737437021e40ecb246b972270024aa641f` for BOTH new runs.
Human decision: [APPROVED BY PRODUCT OWNER, qualitatively](conversational-polish-human-review-2026-10-03.md).
Ticket 12 remains **in-progress**. Phase B is released for the next stage by
the product owner's explicit condition, but **was not executed**.

## Small correction and durable state

The existing planner already proposed a one-time cancellation recovery question,
but a model-requested handoff took precedence before that question was committed.
A failing application/SQLite test reproduced the live failure.

`appointment_intake.py` now applies precedence only to the first simple
cancellation question and explicit generic `model_requested_handoff` /
`appointment_change_requested` codes. It preserves unknown/free-text reasons,
independent risk/human/complaint Intents and selected Knowledge policies; the
entire proposal still passes the unchanged grounding finalizer. Shared
`APPOINTMENT_EXTRACTION_INSTRUCTIONS` distinguishes offering recovery from
executing cancellation, without changing factual or multi-intent instructions.

A second failing test proved that `appointment_change` on “Pode ser outro dia”
returned prematurely before resolving the pending cancellation choice. That
answer now continues the same bounded reschedule episode.

No schema/migration or persistence change. Existing `recovery_offered`,
`request_kind`, `awaiting_field`, `clarification_count`, episode token and inbound
cursor remain atomically committed with reply/outbox/processing/handoff.
Replay/restart cannot repeat the offer; firm refusal/confirmation transfers
without pressure. No real calendar operation or availability statement.

## Offline verification and independent reviews

**767 tests passed**, including 21 added parameterized cases and the strengthened
cancellation replay/restart test. Two new failures were demonstrated before
their corrections. Coverage includes initial generic handoff, unknown genuine
handoff reasons, firm cancellation, confirmation, new preferences, replay,
restart, technical risk, explicit human request, invalid refs and selected policies.
Both adapters receive the same cancellation instruction via deterministic fakes.

Ruff check, Ruff format --check (171 files), compileall, pip check and
git diff --check passed. Existing Starlette/AnyIO deprecation warning remains.

- Product/spec: APPROVE; no material findings after correction.
- Standards: APPROVE; no documented violation or actionable heuristic finding.
- Safety: initial blocker found arbitrary free-text handoff reasons being
  normalized into the generic override. Red regressions reproduced allergy,
  owner request and serious complaint suppression. Raw-code comparison fixed it;
  final independent re-review APPROVE, no remaining material finding.

These reviews and checks finished before either paid run. `grounding.py`,
`reply_plan_instructions()`, handoff persistence, Knowledge, provider selection,
model/configuration, pricing and latency instrumentation remain unchanged.

## Authorized runs

Same configuration: `gpt-6.1-sol`, medium, default/standard, max output 512,
observation deadline 30s, one execution per case, zero retries. Production
deadline remains 10s; measured latency never uses the diagnostic metric as a gate.

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --case appointment-cancellation --output work/evals/openai-cancellation-retest-2026-10-03-01
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --smoke-only --output work/evals/openai-conversational-polish-smoke-2026-10-03-04
```

The isolated case completed at **2026-10-03 20:24:13 BRT / 23:24:13 UTC**:
all three checks pass; model handoff=false, no finalizer handoff or fallback.
Observed trusted reply:

> Sem problema. Você quer cancelar mesmo ou prefere tentar outro dia/horário?

Only after that pass, the fresh ten-case smoke completed at
**2026-10-03 20:25:25 BRT / 23:25:25 UTC**. No historical sample was reused;
all ten cases ran once and every applicable check passed.

| Measure | Isolated retest | Fresh smoke 04 |
| --- | ---: | ---: |
| Cases executed / pass / fail | 1 / 1 / 0 | **10 / 10 / 0** |
| Failed critical checks | 0/2 | **0/17** |
| Grounding | 1/1 | **9/9** |
| Dedicated Intent | 0/0 (not applicable) | **1/1** |
| Handoff policy | 1/1 | **8/8** |
| Appointment safety | 1/1 | **2/2** |
| Persona surface evaluable / pass / fail | 0 / 0 / 0 | **1 / 1 / 0** |

Denominators are applicable checks, not a claim that every case scores every
dimension. Grounding includes composite appointment checks. The one automated
persona surface check is not a human naturalness score.

## Accounting and latency

| Measure | Isolated retest | Fresh smoke 04 |
| --- | ---: | ---: |
| Calls / retries / paid failures | 1 / 0 / 0 | 10 / 0 / 0 |
| Completed model replies / safe generation fallbacks | 1 / 0 | 10 / 0 |
| Input / output / reasoning tokens | 1,891 / 114 / 41 | 19,084 / 1,422 / 477 |
| Cache-read / cache-write / ordinary input | 0 / 1,888 / 3 | 13,192 / 5,862 / 30 |
| Estimated cost | **US$0.005866** | **US$0.0302542** |
| Cost / 1,000 completed model replies | US$5.866 (n=1) | US$3.02542 (n=10) |
| Hard cap | US$0.20 | US$1 |

Combined estimated spend: **US$0.0361202**. Valid complete usage for every call;
reasoning is included in output and not billed twice. No retry, unknown billing,
incomplete response or paid failure. Versioned pricing, settlement totals and
every pre-submission reservation reconcile independently; both caps respected.

| Latency (ms), fresh smoke n=10 | p50 | p95 | max | Above 8s |
| --- | ---: | ---: | ---: | ---: |
| Model request | 3,644.14 | 5,868.29 | 6,001.00 | 0/10 |
| Observed eval E2E | 4,017.37 | 6,270.32 | 6,430.51 | 0/10 |
| Production-equivalent diagnostic | 3,675.26 | 5,900.08 | 6,034.87 | 0/10 |
| Input counting | 323.91 | 443.67 | 487.81 | 0/10 |

Isolated model/E2E: **4,071.00 / 5,196.12ms**. The official observed p95 <=8s
gate **passes this fresh smoke**; it is unchanged. The model dominates latency.
The diagnostic E2E does not approve a production gate. Ten samples do not prove
production tails; real WhatsApp E2E remains pending.

## Human approval, evidence and next gate

**human conversational review: APPROVED BY PRODUCT OWNER**.
Naturalness, clarity, persona and commercial direction are approved qualitatively
from the prior observed responses. No new numerical ratings or retrospective
average are required. Functional smoke is now **10/10**; Case 8 is corrected.
**Phase B released for next stage; NOT executed here.**

Exact synthetic scenarios and trusted replies:
`work/evals/openai-conversational-polish-smoke-2026-10-03-04/human-review.md`
and `human-review-formulario.md`, exactly ten unchanged answers, ratings blank.
These are evidence packets, not a demand for another scored review.
`product-owner-review.json` records the qualitative decision separately from
the collector's generic `pending_human_review` metadata. No automatic scores or
claim that the owner individually rated these ten new outputs.

Both LiveRecords, privacy checks, summary/cost/journal reconciliation and reply
hashes validate. All **107** pre-existing artifact files remain byte-identical.
No secret output, real Customer, Anthropic call, Meta/WhatsApp, real Appointment,
false cancellation/availability, invented discount, fabricated reference,
automatic selected-fact obligation, credentials change or main merge.

Residual gates: broader Phase B and repeated probabilistic coverage, real Meta
smoke blocked on App Secret, real-provider latency; cross-provider comparison
remains deferred. Novel risk detection still depends on existing model signals
and fixed rules; unknown proposed handoffs remain fail-closed. No full V1 or
production approval is claimed; Ticket 12 stays **in-progress**.
