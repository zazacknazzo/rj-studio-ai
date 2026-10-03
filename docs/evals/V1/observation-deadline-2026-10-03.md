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
