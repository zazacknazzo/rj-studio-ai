# Multi-fact handoff diagnosis — Ticket 12

Product-owner authorization: one diagnostic execution of
`grounding-multiple-facts`, US$0.20 hard cap, no retry or Phase B. Model, prompt,
schema, selected synthetic facts and configuration remain unchanged:
`gpt-6.1-sol`, medium, standard/default, 512 output tokens.

## Existing evidence

The complete ten-case 512-token run remains immutable at
`work/evals/openai-smoke-512-2026-10-02-01/`, revision `dcb6fdc`.
Its last sample records successful generation, failed factual/handoff checks,
and a passing price-plus-hours Intent check. The private blind packet contains
the final persisted handoff confirmation. No model proposal, finalizer reason
or decision trace was retained; temporary synthetic SQLite was removed by the
harness. These artifacts cannot prove where the handoff originated.

The record's failed checks and missing expected facts provide a reproducible
artifact assertion. Candidate causes, in probe order: incomplete model plan,
model-requested handoff, deterministic policy, knowledge selection/scoring.
They remain hypotheses until new structured evidence distinguishes them.

## Sanitized trace

Version-4 live records add `decision_trace` to each sample. Version-3 records
remain readable without a trace and are never rewritten. Metadata only:
selected fact IDs, proposed Intents/references/part kinds/fact parts, proposed
handoff, normalized reason, actual finalizer handoff/reason/override, final
rendered fact IDs and safe-fallback flag. Unknown model references become
`unavailable-reference`; raw reasons become controlled `HandoffReason` codes.
No model prose, factual claim values, Customer body, provider payload, auth
header, reasoning text or CoT enters this trace.

The adapter projects metadata **before** structural/reference validation, so
adapter rejection is distinguishable from a finalizer override. The isolated,
serial eval temporarily observes the actual application finalizer call,
delegates unchanged and restores the seam on success or exception. No production
file, provider factory or runtime observer is changed. For a proposed handoff,
a pure deterministic reason-marker probe distinguishes the model branch from
an earlier trusted policy even when both have the same reason label. Its result
is never returned, sent or persisted. No second model is called.

Final rendered IDs are taken from finalized trusted references that appear in
the actual finalized text and persisted reply, including mandatory policies
added by the finalizer outside the proposed AST. Later intake overrides can produce a trusted persisted
handoff code with `finalizer_handoff=false`. `whether_safe_fallback_was_used`
includes deterministic safety overrides as well as generation-failure fallback;
it does **not** change the separate model-reply/cost accounting definitions.

Use this observer only in the isolated serial eval CLI, never in a shared live
application process. A diagnostic success cannot approve the full smoke or B.

## Authorized single-case command

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --case grounding-multiple-facts --output work/evals/openai-multiple-facts-diagnostic-2026-10-03-01
```

`--case` selects exactly one fixture once and enforces US$0.20 for both phase
and global spend. Even a passing case cannot start B. Existing fsynced
reservations, real usage accounting, stateless requests, privacy checks and
no-automatic-retry behavior remain unchanged. No Anthropic, Meta or WhatsApp.

## Result

Executed **2026-10-03 11:04:32 UTC**, revision
`ee85b3da1634f482c63dc5c543e0c765552563d6`. Private, ignored evidence:
`work/evals/openai-multiple-facts-diagnostic-2026-10-03-01/`.

**Classification: B — MODEL_PLAN_INCOMPLETE.**

| Observed stage | Sanitized evidence |
| --- | --- |
| Actual selection | `price-corte`, `hours-corte` |
| Model Intents | `price`, `hours` |
| Model knowledge references | empty |
| Proposed part kinds / factual references | one `phrase` / empty |
| Proposed handoff / normalized reason | `false` / absent |
| Actual finalizer | handoff `true`, `missing_critical_fact` |
| Deterministic override | `missing_critical_fact` |
| Facts rendered in persisted reply | none |
| Persisted reply | verified equal to controlled handoff confirmation |
| Trace safety outcome | `whether_safe_fallback_was_used=true` |

The model had both approved synthetic facts and identified both requests, but
omitted their factual AST parts and references. The finalizer's required-category
check therefore rejected the incomplete plan. This is not model-requested
handoff, missing Knowledge, malformed output, truncation, or a scoring mismatch.
The deterministic rule correctly enforces Ticket 09; weakening it is not warranted.

Request hash and suite/Knowledge/prompt/schema fingerprints match the historical
failed sample exactly. The same failure is reproduced with its origin now visible.
The historical proposal was not retained, so its exact internal path cannot be
recovered retroactively; attribution above describes the new identical-input run.
All 29 historical evidence files remain byte-for-byte unchanged.

### Accounting and gates

- One paid generation, one complete/schema-valid model decision, zero retries,
  paid generation failures or separate generation-failure fallbacks.
- Input 1,326 tokens: 0 cached-read, 1,323 cache-write; output 162, including
  78 reasoning tokens. Only token counts are retained, never reasoning text.
- Settled estimated cost **US$0.0049335**, below the **US$0.20** hard cap;
  cost per 1,000 completed model replies **US$4.9335**, denominator 1.
- Model latency 6,323.46 ms; synthetic persistence-to-fake-acceptance E2E
  7,478.10 ms. One sample is not a useful population percentile or provider gate.
- Two failed critical checks out of two: grounding 0/1, handoff 0/1;
  Intent 1/1. Persona and appointment dimensions have no cases in this diagnostic.
- A complete proposal rejected by a trusted policy remains a completed model
  decision for accounting; the trace's safety-outcome flag is distinct from a
  paid generation failure or separately counted system generation fallback.
- Phase B was **not executed**. Ticket 12 remains **in-progress**; cross-provider
  comparison deferred and human/operational review pending.

### Checks and independent review

585 full-suite tests passed; the 12 trace tests also passed independently.
Ruff check, format check (151 files), compileall, pip check and diff checks passed.
One existing Starlette/AnyIO deprecation warning remains.

Standards: no actionable findings. Spec: one missing trace entry for a mandatory
policy rendered outside the proposed AST; fixed in the eval observer with a
red-to-green regression and independently confirmed resolved. Production
rendering, persistence, messaging, model configuration and prompts are unchanged.

### Proposed next change — not implemented

Add a small provider-neutral instruction to the existing reply-plan instructions:
for every detected factual Intent that has a relevant approved selected fact,
include its factual `reply_part` and declare its reference; handle each Intent in
the same plan. Clarification/handoff remain available when facts are missing or
trusted policy requires them. Do not infer a universal no-handoff rule from fact
count or hardcode a case. Keep the existing schema, trusted renderer and guards.

This is a proposal for product-owner review, not a prompt change or authorization
for another paid run. No further call, Phase B, Anthropic, Meta, WhatsApp or real
Customer was used; no secret was displayed.
