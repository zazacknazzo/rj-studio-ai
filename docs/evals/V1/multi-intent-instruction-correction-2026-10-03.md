# Multi-intent reply-plan instruction correction — Ticket 12

Product-owner authorization follows the confirmed MODEL_PLAN_INCOMPLETE diagnosis.
The previous local commits e9f4b6c, ee85b3d and 2002de4 were published on
`codex/v1-ticket-12-openai-live-eval` before this change. No main merge.

## Minimal change

`livia_persona.reply_plan_instructions()` is already shared by the Anthropic
runtime adapter and the OpenAI eval adapter. Add the rule once there: each
recognized factual Intent supported by selected approved Salon Knowledge must
include its corresponding knowledge references and factual parts for every fact
needed to cover all factual Intents. Nonfactual Intents need no fact. Missing
support must not create references or facts; legitimate handoff remains allowed.

No schema, Knowledge, finalizer, renderer, handoff, intake, messaging, provider
selection or generation configuration change. The deterministic tests cover
request-contract propagation and trusted safety behavior; they do not prove
model compliance. Live retesting supplies that probabilistic evidence.

The eval-only `--smoke-only` option prevents the previous automatic A-to-B
promotion and applies a US$1 global cap. Single-case mode keeps its US$0.20 cap;
these scopes are mutually exclusive. Both preserve real usage accounting and
stop immediately on a failed check or generation/accounting/privacy failure.

## Authorized sequence

1. Run all checks and independent review; commit the correction.
2. One `grounding-multiple-facts` execution, no retry, cap US$0.20:

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --case grounding-multiple-facts --output work/evals/openai-multi-intent-retest-2026-10-03-01
```

3. Only if it passes, run a fresh homogeneous ten-case smoke, no retries,
   cap US$1. Stop at the first failed case. Never execute B in this stage:

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --smoke-only --output work/evals/openai-multi-intent-smoke-2026-10-03-01
```

All calls use gpt-6.1-sol, medium, standard/default and max_output_tokens=512.
Synthetic fixtures, temporary SQLite and deterministic fake delivery only;
no Anthropic call, Meta, WhatsApp, real Customer, credential change or CoT.
Historical artifacts are immutable. Ticket 12 remains in-progress and human
review remains required even if these runs pass.

## Results

Correction committed at `1faf39052d9471805d320553845940e8a1fe5ff5` after
297 focused tests and the full **600-test** suite passed. Fifteen tests were
added: fourteen provider/decision/safety contract cases and one passing ten-case
smoke demonstrating no automatic B and a US$1 cap. The initial adapter-instruction
checks failed before the shared paragraph; the smoke-only test also failed before
its scope control. Ruff check, format (152 files), compileall, pip check and diff
checks passed. One existing Starlette/AnyIO deprecation warning remains.

Independent Standards and Spec reviews reported no actionable findings. The
Anthropic adapter was exercised through an offline recording fake only; no
external Anthropic request or credential use occurred.

### Isolated live retest — blocked

Executed **2026-10-03 11:18:57 UTC**, at the correction commit above. Private,
ignored artifacts: `work/evals/openai-multi-intent-retest-2026-10-03-01/`.

| Indicator | Observed result |
| --- | --- |
| Requested configuration | gpt-6.1-sol / medium / standard-default / 512 |
| Live generation submissions / retries | 1 / 0 |
| Valid completed model replies | 0 |
| Separate system safe fallbacks | 1 |
| Stop code | `live_usage_missing_or_invalid` |
| Verified usage / actual cost | unavailable / indeterminate |
| Conservative spend reservation | **US$0.0112425**, cap **US$0.20** |
| Model attempt / synthetic E2E latency | 7,936.21 / 9,030.51 ms |
| Critical gate failures | 2/2, both **not evaluable** |
| Grounding / Intent / handoff / appointment safety | 0/0 each; no evaluated model output |
| Full ten-case smoke | **not executed**, cost US$0 |
| Phase B | **not executed** |

The record contains one failed attempt with `billable=null`, `usage=null` and
`pricing_verified=false`. The journal preserves a reservation before submission
and settles conservatively with missing usage, blocking further work. The actual
charge cannot be inferred from the reservation. Cost per 1,000 completed model
replies is undefined because the denominator is zero; no paid-failure fallback
inflates it. The two gate failures do not constitute observed hallucinations.

Both synthetic facts reached context, but no proposal metadata or finalizer
result exists for this execution. The safe local outcome is not an evaluated
model answer. Therefore this run cannot confirm or refute the correction's effect
on the original incomplete-plan failure. The persisted error code does not prove
whether the underlying issue was transport, an interrupted response or invalid
usage; latency alone is insufficient. No additional call or retry was performed.

The full-smoke output directory was never created. All 35 previous historical
artifact files remained byte-for-byte unchanged. No secret, real Customer,
Meta/WhatsApp action or external Anthropic call; no main merge. Protected files
(schema, grounding/finalizer, Knowledge, handoff/intake, messaging/providers and
selection) are unchanged. The system never fabricates refs or completes the
model's plan.

Ticket 12 remains **in-progress**; B and human approval remain pending. Next
blocker: establish the generation/usage failure before any further authorized
live execution. Do not relax grounding or claim this retest passed.
