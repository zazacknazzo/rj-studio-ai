# OpenAI Low runtime promotion

Status: implementation; local integration smoke pending.
Approved scope: product-owner request of 2026-10-05. Intelligence is validated
enough; Agentic Surface is approved/frozen. Ticket 12 remains in-progress.

Previously `generator_from_settings` constructed fixed or Anthropic generation;
OpenAI existed only in the live eval collector. It now also constructs OpenAI:

```text
Canonical inbound → SQLite admission → Processing Executor
→ configured ReplyGenerator → untrusted LLMDecision → existing trusted finalizer
→ atomic AIReply + OutboundDelivery + processing/handoff/intake completion
→ existing Outbound Executor
```

The Responses wire contract lives in `providers/openai_contract.py`: the existing
instructions, request/schema, output extraction, completion check and strict
usage parser are shared with eval. No intelligence instructions were changed.
The runtime adapter performs one async Responses request without transport
retries or eval token-counting/bookkeeping. Its bounded cancellation covers
request and cleanup. Production still has 10 seconds total and a 1-second
finalization margin; eval's 30-second observation deadline is not promoted.

## Configuration and failures

Select `LLM_PROVIDER=openai` with `OPENAI_API_KEY` privately configured.
`OPENAI_MODEL=gpt-6.1-sol`, `OPENAI_REASONING_EFFORT=low` and
`OPENAI_MAX_OUTPUT_TOKENS=1024` are the approved defaults. Explicit medium effort
or a lower output limit are supported overrides; unsupported model/effort/cap
or provider names fail validation. `LLM_PROVIDER=fixed` remains the safe local
default. Existing Anthropic composition is unchanged; no cross-provider fallback.

A missing key makes configuration/readiness fail without issuing a request.
Auth/request rejection, incomplete output, invalid schema/reference or
missing/incoherent usage fail closed. Timeout/transport/429/5xx use the existing
bounded generation failure semantics (at most two core attempts, same deadline);
no retry mechanism was added. The proactive core already finalizes exhausted or
permanent failures with its safe generation-unavailable policy and durable
handoff; no provider output bypasses policy or sends directly to messaging.

Migration `0013_openai_generation_metadata` adds nullable counts for cached
input/cache writes/reasoning and allowlisted response status/incomplete reason.
Old evidence remains intact. Unknown counts remain null, never zero. Runtime
cost estimates remain null without an approved runtime price table; the local
smoke uses the existing versioned rates and a conservative spend reservation.
No output, reasoning text, raw provider errors or secrets enter metrics.

## Validation and remaining blockers

Offline tests cover selection/config, request/usage, failures, total cancellation,
trusted price rendering, handoff and appointment authorization, durable completion,
restart/replay, migration data preservation and interrupted migration rollback.
Local smoke must use synthetic SQLite/Knowledge, the real runtime factory and
application lifespan/Processing Executor, and exclusively fake outbound acceptance.
Its ceiling is US$0.25; latency is diagnostic, not a waiver of existing product gates.

Real messaging integration/Meta smoke remains a separate operational gate.
Meta App Secret and real channel validation remain blockers. This promotion
must not be described as WhatsApp production-ready or complete Ticket 12.

Official Responses contract: [create response](https://developers.openai.com/api/reference/python/resources/responses/methods/create).
