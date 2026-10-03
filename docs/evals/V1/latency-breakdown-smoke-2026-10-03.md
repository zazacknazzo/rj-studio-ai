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
