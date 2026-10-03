# Latency breakdown and new OpenAI smoke

Product-owner authorization: add only privacy-safe latency decomposition, then
execute a fresh ten-case `SMOKE_CASES` run once per case with US$1 cap and
`--smoke-only`. Phase B is prohibited. Ticket 12 remains **in-progress**.

## Measurement contract

Live record version 6 adds `latency_breakdown` to each execution. Historical
versions 3–5 remain readable and unchanged; absent measurements remain null.
Model latency now measures precisely the HTTP `/responses` request through
complete receipt, including failed requests. Response parsing, usage/schema
validation and trusted finalization have separate durations. Earlier records
retain their original model timings, which also included parsing/validation.

All components are nonnegative milliseconds, with exclusive nested timing:

| Component | Boundary |
| --- | --- |
| admission_ms | Synthetic inbound admission and generation claim |
| input_count_ms | `/responses/input_tokens` and count validation |
| budget_reservation_ms | Durable spend reservation |
| model_request_ms | `/responses` HTTP request only |
| decision_validation_ms | Response/usage/schema/privacy validation, excluding trace bookkeeping |
| trusted_finalization_ms | Actual deterministic trusted finalizer, once |
| persistence_ms | Generation metrics, reply/outbox completion and failure release |
| fake_outbound_ms | Fake delivery runner, including its durable outbox transitions |
| eval_bookkeeping_ms | Fixture-context preview, decision trace/probe, spend settlement and request evidence |
| unattributed_ms | Remaining measured time, including actual context/policy work and observer overhead |
| observed_eval_e2e_ms | Same original E2E: before admission through fake Provider Acceptance/failure |

Known components plus unattributed time reconcile to observed E2E within 1ms.
Unentered stages remain null, never an assumed zero. Zero is valid only for an
entered stage with measured zero duration. Partial records retain unknowns and
cannot produce a complete diagnostic. Aggregates report observed/missing counts
alongside p50/p95/max and counts above eight seconds.

`production_equivalent_e2e_ms` is diagnostic only:

```text
observed_eval_e2e_ms
  - input_count_ms
  - budget_reservation_ms
  - eval_bookkeeping_ms
```

It retains model request, validation, finalization, persistence, fake-outbound
state transitions and all unattributed time. No unexplained residual is
reclassified as removable eval overhead. Fake outbound remains a placeholder;
real WhatsApp network/queue/delivery evidence is absent. This metric does not
predict actual production latency and cannot approve or replace the official
**p95 billable observed E2E <=8s** gate without an explicit spec decision.

Instrumentation is confined to `evaluation/`: scoped observation of the isolated
store instance and existing eval finalizer observer. Production defaults remain
10s/1s, with unchanged providers, prompts, model config, grounding, finalizer,
handoff, pricing and retry policy. Observation stays 30s/1s, no automatic retry.

## Authorized smoke

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --smoke-only --output work/evals/openai-latency-smoke-2026-10-03-01
```

Configuration: `gpt-6.1-sol`, medium, default/standard, 512 output tokens,
30-second observation deadline; ten cases once, US$1 cap. Semantic/safety,
usage, timeout, accounting or privacy failures stop the run. Slowness alone
is recorded as a failed latency gate and does not stop remaining valid cases.
No historical run is reused. Checks and actual result will be recorded below.

## Checks and actual smoke

The three prior commits were published before editing; origin was confirmed at
`941114ec4ed2bf84a9505bee6e4c7f2a6ed17efc`. No main merge.
Instrumentation revision: `8fed9c90f3bd116582b7fec0fa71456b463d22e1`.
All **670 tests** passed (23 new cases), including 320 focused evaluation,
application/deadline, grounding, durable handoff and appointment regressions.
Ruff check/format, compileall, pip check and diff checks passed. One existing
Starlette/AnyIO warning remains. Independent Standards and Spec reviews had
zero findings; reviewers made no network/paid calls.

Fresh run recorded at **2026-10-03 14:47:27 UTC** under
`work/evals/openai-latency-smoke-2026-10-03-01/`. All ten `SMOKE_CASES` executed
once in their declared order; **10 pass / 0 fail**, no unexecuted cases or B.
All received completed valid decisions and usage; no truncation, prohibited
claim, generation failure, privacy/accounting failure, retry or system fallback.
The one sample over eight seconds did not fail the semantic run or become a
provider failure. All stages were observed for all ten executions, and the
maximum per-execution reconciliation error was **0ms**.

| Semantic measure | Result |
| --- | --- |
| Failed critical checks | **0/18** |
| Grounding | **9/9** |
| Intent | **1/1**, the explicit multi-intent oracle |
| Human Handoff correctness | **9/9** |
| Appointment safety | **2/2** |
| Context | **2/2** |
| Persona evaluable / pass / fail | **1 / 1 / 0** |

These are applicable checks, not a claim of full Intent/persona suite coverage.
Human naturalness review is still pending.

| Cost measure | Result |
| --- | --- |
| Live calls / retries / paid failures | **10 / 0 / 0** |
| Completed model replies / separate system fallbacks | **10 / 0** |
| Input / output / reasoning tokens | **13,750 / 1,597 / 594** |
| Cache-read / cache-write / ordinary input tokens | **8,106 / 5,614 / 30** |
| Total cost, unchanged versioned pricing | **US$0.0308756** |
| Cost per 1,000 completed model replies | **US$3.08756**, denominator 10 |
| Hard cap | **US$1; respected** |

Reasoning is included in output tokens, not charged again. Cost independently
reconciles from the token partitions using the unchanged rates; paid failures
would still contribute cost without increasing the completed-reply denominator.

| Latency, milliseconds | p50 | p95 | Maximum | Above 8s |
| --- | ---: | ---: | ---: | ---: |
| Model HTTP request | 5,494.95 | 7,616.46 | 8,348.30 | 1/10 |
| Observed eval E2E | 5,877.60 | **7,987.64** | 8,725.87 | **1/10** |
| Production-equivalent diagnostic | 5,524.92 | 7,645.94 | 8,378.23 | 1/10 |
| Input counting | 343.43 | 833.77 | 1,102.11 | 0/10 |

The unchanged observed p95 gate **passes for this ten-case smoke**, by only
**12.36ms**. It was not passed using the diagnostic. Real WhatsApp E2E and the
overall operational gate remain pending; ten single-run cases and an interpolated
p95 do not establish a robust production latency distribution. Earlier runs,
including slow and unknown-usage attempts, remain historical evidence and are
not erased or replaced by this run. No overall V1 gate approval is claimed.

The slowest case was `grounding-multiple-facts`: model **8,348.30ms**, observed
**8,725.87ms**, diagnostic **8,378.23ms**, input count **343.73ms**. It passed all
three semantic checks and rendered both approved synthetic facts without handoff.
Its model call alone exceeded eight seconds, so this excess primarily comes
from model/request latency; removing eval overhead cannot fix that sample.
Model requests account for **92.39%** of this run's summed observed time.
This does not distinguish provider inference from network time inside that request.

`LiveRecord` validation and independently recomputed summaries passed. The
multi-fact request hash and suite/Knowledge/prompt-schema fingerprints match the
preceding isolated retest exactly. All **53 files across six historical runs**
remain byte-for-byte unchanged. Component percentile populations name their
observed/missing counts; component percentiles must not be added as if they were
one execution's timeline.

Private human review packet: `human-review.md` and `human-review.json` in the new
run directory, **10 synthetic answers**, unscored with status `pending`.
No Anthropic, Meta/WhatsApp, real Customer, secret output or credential change.
No production files, prompts, model/effort/output limit, grounding, finalizer,
handoff or pricing were changed. **Phase B was not executed**; Ticket 12 remains
**in-progress**, with human and real operational evidence still pending.
