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

Pending required checks, independent review and authorized retests.
