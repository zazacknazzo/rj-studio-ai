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
Suppressed turns never call the model.

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

Prepared; live results will be recorded after the controlled command.
Cross-provider comparison and human review remain pending. No Meta smoke.
