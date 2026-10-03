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

Pending required checks, independent review and the one authorized execution.
No prompt/schema/model change or speculative production fix is authorized.
