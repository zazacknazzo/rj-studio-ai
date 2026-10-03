# Live eval observation deadline

Product-owner authorization: fix only the eval observation budget, then run
`grounding-multiple-facts` once with a US$0.20 cap. No full smoke or Phase B.
Ticket 12 remains **in-progress**; human and operational review remain pending.

## Cause and smallest seam

Previously `MessageResponder.process_persisted()` started a 10-second deadline
after claim, reserved one second for finalization, and passed `work_budget()` to
the eval generator. Token counting consumed that same budget before `/responses`.
Both HTTP calls used the remaining value as their phase timeout. After generation,
the responder also rejected exhausted work budgets. Increasing only the HTTP
timeout would therefore not allow a slow valid response to complete.

The optional `execution_deadline` argument lets the eval supply an observation
deadline. When omitted, the same deadline starts at the same point with unchanged
**10-second total / 1-second finalization margin**. Production ProcessingRunner,
webhooks, provider selection, leases, retry policy and messaging are unchanged.

## Observation versus product latency

- Eval starts one **30-second observation deadline** immediately before inbound
  admission. The existing one-second finalization margin leaves at most 29 seconds
  for context, token counting and generation; no new budget per stage or attempt.
- `/responses/input_tokens`: connect/read/write/pool capped at five seconds or the
  smaller remaining budget. No retry. Actual elapsed time reduces the remaining
  observation budget; slow counting does not get the whole model read window.
- `/responses`: connect/write/pool capped at five seconds or remaining work budget;
  read bounded by that remaining budget after counting. No automatic retry.
- HTTPX timeouts bound network phases/inactivity, not an independent whole-request
  wall clock. The adapter also checks elapsed observation time after receiving
  status/usage: a late response fails closed with `live_observation_timeout`,
  retaining received usage and known cost. A read timeout without a Response
  retains unknown usage/cost and the conservative reservation.
- The eval collector preserves those attempt records even if the production
  responder cannot persist a safe fallback after expiry/loss of its claim. Such
  an execution is `failed` with no reply; neither a completed reply nor a fallback
  is fabricated. Validation/finalization exhausting the work budget also produces
  a controlled observation failure. Production ownership rejection is unchanged.
- Model latency measures only `/responses`. E2E still starts before admission
  and includes context, token counting, generation, finalization and fake Provider
  Acceptance. Fixture setup is excluded; preflight is not excluded.
- The product threshold stays **p95 billable E2E <=8 seconds**. A 12-second model
  answer can be evaluated, but fails the measured latency gate. Slowness alone
  does not become a provider failure. A failed/unknown measured gate cannot
  promote an otherwise passing smoke to B.
- `measured_latency_gate` uses the billable population and is explicitly scoped
  to synthetic persistence through fake acceptance. A pass cannot approve the
  real operational gate, which stays `pending_real_provider_evidence`.

Model, effort, tier, output limit, shared multi-intent instructions, schema,
grounding, finalizer, handoff and pricing are unchanged. No real Customer data,
WhatsApp submission, Meta smoke or Anthropic call is involved.

## Validation and controlled probe

Deterministic regressions cover production defaults, explicit observation
deadline, a complete 12-second response with usage and a failing latency gate,
the inclusive eight-second threshold, bounded token-count preflight, timeout
without retry/known cost, and late complete response with retained usage/cost.
The independent review found two evidence-loss paths: late-response fallback
after the real UTC lease expires, and work-budget exhaustion during decision
validation/finalization. Both now have deterministic regressions (including
shared monotonic/UTC clocks) and eval-only handling. Results and the single
authorized probe will be recorded below after checks.

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --case grounding-multiple-facts --output work/evals/openai-observation-deadline-2026-10-03-01
```

Only one new run is authorized: `gpt-6.1-sol`, medium, default/standard,
`max_output_tokens=512`, no retries. Historical artifacts remain unchanged.

## Checks and live result

Executed **2026-10-03 14:13:09 UTC**, code revision
`9244f82a69bffdb12dffaa22b85853b8b85a2cf9`, branch
`codex/v1-ticket-12-openai-live-eval`. Initial commits `d56d764` and `80ada33`
were published to origin before changes; no main merge.

All **647 tests** passed before the paid call (13 added cases); 297 focused
evaluation/application/deadline/grounding/handoff/appointment regressions passed.
Ruff check and format, compileall, pip check and diff checks passed. One existing
Starlette/AnyIO deprecation warning remains. Standards review: no findings.
Spec review: two evidence-loss findings corrected, then no remaining material
findings. No network/paid calls were made by reviewers.

Private, ignored artifacts: `work/evals/openai-observation-deadline-2026-10-03-01/`.
The record validates with `LiveRecord`; all 47 files in the five historical runs
remain byte-for-byte unchanged. Request, suite, Knowledge and prompt/schema
hashes match the preceding timeout probe exactly.

| Measure | Result |
| --- | --- |
| Generation calls / retries / paid failures | 1 / 0 / 0 |
| Response / HTTP status / usage | completed / 200 / present and valid |
| Completed model replies / system safe fallbacks | 1 / 0 |
| Input / output / total tokens | 1,425 / 314 / 1,739 |
| Cache read / cache write input tokens | 0 / 1,422 |
| Reasoning tokens | 160, already included in output tokens |
| Cost under unchanged versioned pricing | **US$0.006701** |
| Cost per 1,000 completed model replies | US$6.701, diagnostic N=1 |
| Model p50/p95 | **9,804.85 ms** |
| Synthetic billable E2E p50/p95 | **11,218.25 ms** |
| Critical failed checks | **0/2** |
| Grounding / Intent / handoff correctness | **1/1 / 1/1 / 1/1** |
| Appointment safety | 0/0, not applicable to this case |
| Measured latency gate | **FAIL**, threshold unchanged at 8,000 ms |
| Operational latency gate | pending real provider evidence |
| Hard cap | US$0.20; respected |

Sanitized trace confirms selected facts `price-corte` and `hours-corte`, proposed
Intents `price` and `hours`, both Knowledge references and two corresponding
`fact` reply parts. Model and finalizer both selected handoff=false; both facts
were rendered, with no override or safe fallback. **The isolated semantic case
passes**, while its measured latency fails. One sample does not prove robust
p95, general multi-intent reliability, naturalness or operational readiness.

Cost is 3 ordinary input tokens at US$2/M, 1,422 cache-write tokens at US$2.50/M
and 314 output tokens at US$10/M. No second reasoning-token charge, fabricated
usage or fallback inflating the denominator. No pricing configuration changed.

Stopped after the single authorized case. No full smoke, B, Anthropic,
Meta/WhatsApp, real Customer, secret output, credential changes or production
deadline increase. Grounding, finalizer, handoff and multi-intent instructions
remain unchanged. Ticket 12 remains **in-progress** with human/operational gates
and cross-provider comparison pending/deferred.
