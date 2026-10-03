# Responses usage diagnosis — Ticket 12

The product owner authorized diagnosis only, followed by at most one synthetic
`grounding-multiple-facts` call if existing evidence cannot establish the cause.
No ten-case smoke or B, even on success. Cap US$0.20, no retry; unchanged
multi-intent instructions, model, medium effort, standard/default, 512 output
tokens, pricing, Knowledge, grounding, handoff and production runtime.

## Existing evidence and confirmed defect

Commits 1faf390 and 782870c were published before edits; origin matched
`782870c5ddc9e303621e3fcce1afa0d60dac6831`, working tree clean.
The failed historical attempt remains immutable at
`work/evals/openai-multi-intent-retest-2026-10-03-01/`, revision 1faf390.
It records usage=null, pricing_verified=false and a conservative US$0.0112425
reservation. It retains no HTTP status, Response status, field-presence metadata,
or primary failure code. No provider response ID was retained; store=false.

A deterministic HTTPX read-timeout regression reproduces a **confirmed class F
harness defect**: the previous unconditional `if usage is None` overwrote
transport, HTTP, JSON, status and validation failures with the same generic code.
The original failure cannot be retroactively classified A/B/C/D/F from these
artifacts. It is not proof of API usage absence. Approximate latency is not proof
of timeout either. Adding provenance prevents this loss on the authorized probe.

Ranked hypotheses and distinguishing evidence: transport failure predicts no
received Response and a controlled transport code; absent usage predicts a
received JSON Response with usage_present=false; parsing mismatch predicts
usage_present=true plus a missing/shape code; invariant failure predicts present
counts plus a partition/total code. A noncompleted Response has its actual status
retained regardless of whether usage exists.

## API and implementation boundary

The OpenAI SDK is **not installed**, nor declared or imported by this adapter.
HTTPX **0.28.1** posts to Responses and decodes JSON directly. SDK mapping cannot
have caused this adapter's failure. No SDK was installed or substituted.

[Official Responses reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create)
marks usage optional. Absence or null remains unknown, never zero. The approved
[cache pricing contract](https://developers.openai.com/api/docs/guides/prompt-caching)
uses input total, cache-read and cache-write partitions, and output total.
Rates and LivePricing.cost are unchanged.

Required for exact cost: nonnegative integer input/output/total counts, explicit
cache-read and cache-write counts, sum-consistent partitions and total.
Missing input breakdown or either cache field fails closed; no inferred zero.

Reasoning count is informational: total output already includes it and is billed
at one output rate. Missing optional output breakdown is retained as null and
its aggregate stays unknown; it does not prevent exact cost when every billing
component is available. Provided reasoning counts must still be nonnegative
integers no larger than output total. Invalid shapes/counts are rejected.
A noncompleted Response never releases a quality gate, while verified usage can
still account for its paid failure. Invalid/missing billing usage retains the
worst-case reservation and blocks subsequent submissions, including after restart.

## Sanitized metadata and classification

Live records version 5 require per-attempt response_diagnostics; historical
versions 3/4 remain readable and unchanged. Only allowlisted status, presence
flags, nonnegative numeric counts, controlled validation/transport codes,
SDK version and HTTP success/status are retained. Unknown statuses are normalized.
For no observed HTTP/JSON Response, presence/status fields are null, not false:
absence of an observation is not API usage absence.

No output, reasoning, CoT, provider body, raw exception, Customer Message,
credential/header or raw operational ID is copied into diagnostics.

| Class | Evidence |
| --- | --- |
| A USAGE_ABSENT | JSON Response observed; usage missing/null; usage_absent |
| B USAGE_PARSE_ERROR | Present usage/fields but missing required shape/field code |
| C USAGE_INVARIANT_FAILURE | usage_count_invalid, usage_input_breakdown, usage_output_breakdown or usage_total_mismatch |
| D RESPONSE_NOT_COMPLETED | Observed status is not completed; gate remains blocked |
| E SDK_MAPPING_PROBLEM | Excluded in this direct-HTTPX path |
| F OTHER | Controlled transport/HTTP/invalid JSON failure; not mislabeled absent usage |

## Checks and authorized command

110 evaluation tests and all 634 suite tests passed; 34 new test cases plus the
strengthened read-timeout regression. Ruff check, format (154 files), compileall,
pip check and diff checks passed. One existing Starlette/AnyIO warning remains.
Independent Standards and Spec reviews reported no actionable findings. An
offline deterministic replay produced the same request hash as the historical
failed retest; prompt/schema/configuration are unchanged. The one authorized
probe is pending.

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --case grounding-multiple-facts --output work/evals/openai-usage-diagnostic-2026-10-03-01
```

This selects the fixture once and cannot promote to smoke/B. A fresh private,
ignored record is required; historical files must not be overwritten.

## Live result

Pending. No paid call performed for this diagnosis yet. Ticket 12 remains
in-progress; a probe success alone cannot approve its complete gate.
