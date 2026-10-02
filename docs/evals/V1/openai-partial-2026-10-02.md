# Ticket 12 — partial OpenAI live execution

Product-owner execution revision, 2026-10-02. **Ticket remains in-progress.**
Anthropic comparison is deferred by the product owner; this command makes no
Anthropic request. The approved Sonnet/Terra spec and Phase 1 evidence remain
historical sources. This authorizes OpenAI-only collection, no comparative
acceptance or winner. Production provider selection and `.env` stay unchanged.

## Configuration and accounting

Eval-only `gpt-6.1-sol`, Responses API, `reasoning.effort=medium`,
`service_tier=default` (standard), structured decision, `store=false`, no tools,
reasoning summaries or automatic HTTP retries. Institutional prompts, synthetic
scenarios, selected facts, context, schema and trusted rendering use existing
contracts. Expected decisions/preferences are never sent as model inputs.

The existing **200 total output-token limit** is preserved. Responses includes
reasoning and JSON within that limit, not only the final customer text. A
truncated decision is a paid failure and stops execution; the limit is not
silently increased. [API contract](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

[Versioned pricing](pricing.openai-2026-10-02.json), verified 2026-10-02:
US$2/M ordinary input, US$0.10/M cache read, US$10/M output. The official model
also charges US$2.50/M cache writes, which must not be omitted. Input is
partitioned ordinary/read/write without double counting; reasoning is already
part of output usage. [Model pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[usage accounting](https://developers.openai.com/api/docs/guides/prompt-caching).

Before each paid submission, input-token counting receives the same input and
schema. Add a 1,024-token safety allowance and reserve worst-case input rate plus
all 200 output tokens. Reservation is fsynced before submission; settlement
uses real usage. Missing usage retains the reservation, stops all new calls and
prevents an exact cost claim. An exclusive journal lock prevents simultaneous
collectors. Restart with an unresolved reservation requires manual inspection.
Phase A cap is **US$1**; global A+B cap is **US$5**, including failures/retries.
Wrong tier/model, absent usage, privacy or critical failures stop acquisition.
No raw API exception, body, authorization header or reasoning is exported.

## Operations and evidence

Only after explicit paid-call authorization, from the repository root:

```bash
.venv/bin/python -m rj_studio_ai.evaluation.live --allow-paid --output /absolute/new/private/run-directory
```

Use a new private directory outside Git or under ignored `work/`. Never restart
a stopped run with a new directory to reset spend authorization. Evidence:
spend journal, immutable samples, version-2 phase records, report and single-model
human-review packet. Phase 1's version-1 records/offline commands remain intact.

Phase A: ten cases in `evaluation/live.py:SMOKE_CASES`, one run each. Only after
all pass: Phase B runs all 52 once, then repeats probabilistic grounding,
appointment, handoff and persona cases up to three total runs across A+B.
Suppressed turns never call the model. The pending-delivery context fixture is
an explicit deterministic `delivery_barrier` guard, not a live model context
sample. Bounded/expired history cases reach the model; neither leaves an extra
unprocessed fixture inbound. Live quality denominators exclude no-call guards.
Every Phase A check must pass before B, including clarification and multi-Intent.

Each answer uses actual MessageResponder, claims, trusted rendering, handoff,
intake and completion in isolated synthetic SQLite. Delivery uses only M01's
fake sender. Knowledge selection is fixed to fixture-selected facts to isolate
generation/grounding; bounded context uses the real builder. The grounding
oracle's `Olá!` is a style expectation: live factual scoring preserves all
factual contains/excludes while leaving that greeting to human review.

Model timing measures generation REST only. E2E starts at inbound admission and
ends at **fake Provider Acceptance**, including counting/processing. All billable
attempts/failures remain in cost/latency; suppressed/dry runs cannot dilute it.
Simulated delivery **cannot pass the real WhatsApp operational latency gate**.
Cost includes every billed attempt; persisted logical replies alone form its
denominator. A paid failure plus one durable safe handoff counts as one reply.
Unexecuted plan entries are separate from executed-check denominators.

Human packet: only scenario and final trusted answer, hiding technical metadata.
Failed-generation fallbacks are excluded from model-naturalness samples. Seven
human rubric dimensions remain unscored; no paired comparison or LLM judge.

## Execution status

OpenAI-only live gate **partially executed, blocked**, 2026-10-02 at
23:15:26 UTC (20:15:26 America/Sao_Paulo). Code revision:
`e58d4e309e6c57ad7947c3ddfad3825367a29881`.
Private, Git-ignored evidence: `work/evals/openai-partial-2026-10-02-01/`.

Phase A executed 9 of 10 cases. `persona-incomplete-context` returned
`status=incomplete`, with 200 output tokens (133 reasoning tokens) against the
configured 200-token total limit. No valid structured decision was available;
the application committed its safe handoff reply. The recorded evidence is
consistent with token-budget exhaustion; the provider's detailed incomplete
reason was not retained, so no more specific root cause is claimed.
`grounding-multiple-facts` was not executed. **Phase B was not started.** No
retry, fresh-run restart or token/deadline increase followed the stop.

| Observed population | Result |
| --- | --- |
| Live generation calls / retries / paid failures | 9 / 0 / 1 |
| Input / output tokens | 11,434 / 1,339 |
| Cache read / cache write / reasoning tokens | 7,512 / 3,895 / 516 |
| Completed logical replies | 9: 8 valid decisions plus 1 safe failure handoff |
| Total cost / cost per 1,000 completed replies | US$0.0239327 / US$2.659188889 |
| Model p50 / p95 | 4.961 s / 6.812 s |
| Simulated E2E billable p50 / p95 | 5.332 s / 7.214 s |
| Critical failures | 0/16 executed critical checks |
| Grounding / handoff / appointment safety | 8/8 / 8/8 / 2/2 |
| Intent / persona structural compliance | 0/0 unexecuted / 0/1 |

Real usage was present in all nine attempts. Cost was reconciled independently
against every spend-journal settlement and phase record, including the paid
failure. No known billing was omitted. Both caps were respected. These sparse,
partially stopped samples cannot approve V1; simulated E2E does not replace the
real-provider gate. No prohibited claim was observed in executed critical cases.

Single-model blind packet: `human-review.md` and `human-review.json` in that
directory; eight final answers from valid decisions, no technical metadata,
unscored. The safe fallback is excluded from model-naturalness review.

Remaining blockers: resolve the incomplete structured output within an approved
token/deadline configuration; approve any further paid resumption; finish live
coverage, human review and real-provider operational evidence. Cross-provider
comparison remains deferred. **Ticket 12 remains in-progress**, with comparative
acceptance unchecked. No Anthropic request, Meta smoke, real Customer or
WhatsApp message was used; no credential was displayed or committed.

Validation: 15 new billing/adapter/SQLite runner tests; independent Standards
and Spec reviews approved after fixing context-orphan, smoke-gate and Intent
coverage findings. Full test/check results are recorded with the ticket.

## Historical accounting correction — product-owner clarification

The preceding table and version-2 private artifacts describe persisted logical
AI Replies, including one local safe fallback. They are retained as historical
evidence, not reused by the [new 512-token run](openai-smoke-512-2026-10-02.md).
For **completed model replies**, the correct denominator is **8**, not 9:
US$0.0239327 × 1,000 / 8 = **US$2.9915875**. The ninth call remains a paid
generation failure; its system safe fallback is separate. All nine attempts
remain in the cost and latency populations. The persona result is **0 evaluable,
0 pass, 0 fail, 1 not-evaluable**, rather than an assessed persona failure.
This correction does not make the blocked run pass or authorize Phase B.
