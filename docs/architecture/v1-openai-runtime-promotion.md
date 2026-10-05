# OpenAI Low runtime promotion

Status: **OPENAI LOW PROMOTED TO REAL RUNTIME**; **LOCAL INTEGRATION SMOKE PASS**.
OpenAI Low is the recommended V1 runtime candidate; enable it explicitly.
The safe development default remains fixed.
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
Local smoke used synthetic SQLite/Knowledge, the real runtime factory and
application lifespan/Processing Executor, and exclusively fake outbound acceptance.
Its ceiling was US$0.25; latency is diagnostic, not a waiver of existing product gates.

Real messaging integration/Meta smoke remains a separate operational gate.
Meta App Secret and real channel validation remain blockers. This promotion
must not be described as WhatsApp production-ready or complete Ticket 12.

Official Responses contract: [create response](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

## Local integration evidence — 2026-10-05

Source revision: `b457ec5` (baseline `97fe5f0`). Run:
`work/integration/openai-runtime-2026-10-05-01/report.json`;
`spend.jsonl`, synthetic SQLite/Knowledge and `smoke-driver.py` remain local/ignored.

Steps: start the real `create_app` lifespan using explicit OpenAI settings, a
synthetic ingress adapter and deterministic fake outbound sender; post each
synthetic Message to `/webhooks/whatsapp`; observe durable Processing Executor
completion, trusted reply and outbox; wait for fake acceptance. The canonical
`meta` label is used only for executor filtering; the smoke application receives
synthetic/fake adapters and makes no messaging API call. The only external
destination allowed by the smoke transport
is OpenAI `/v1/responses`. It journals a conservative UTF-8 request-byte input
bound plus protocol allowance and the output ceiling before each submission;
unknown spend blocks further submissions. No input-count endpoint is called.

| Case | Synthetic Customer Message | Observed final reply |
| --- | --- | --- |
| 1 | Oi | Oi! Sou a Lívia, atendente virtual do RJ Studio. Como posso te ajudar? |
| 2 | Quanto custa o corte? | O corte custa R$ 120,00. Quer ajuda para dar o próximo passo? |
| 3 | Qual preço? | De qual serviço você quer saber o valor? |
| 4 | Consegue desconto? | Qual serviço você está pensando em fazer? |
| 5 | Quero corte sexta | Qual período você prefere na sexta? |
| 6 | Quero cancelar meu agendamento | Entendi. Você prefere remarcar ou seguir com o cancelamento? |
| 7 | Quero falar com uma pessoa | Claro! Vou chamar alguém da equipe pra você. |
| 8 | Meu couro cabeludo está ardendo depois da química | Se o procedimento estiver em andamento, pare e procure avaliação profissional. Se houver falta de ar ou sinais graves, procure atendimento médico urgente. Vou chamar a equipe agora. |

Eight inbound Messages, eight valid decisions/replies and eight logical outbox
rows passed; eight sends were **fake**, with acceptance persisted. Human request
and technical risk activated durable handoff. Appointment interest and cancellation
remained collecting (one authorized question each), with no booking, availability,
discount or cancellation promised. The price above is exclusively a synthetic
approved fixture, not a real RJ Studio price.

8 live calls, 0 retries, 0 paid failures, all completed usage validated.
Tokens: 24,639 input (18,390 cached; 6,225 cache-write), 1,168 output including
84 reasoning tokens. No reasoning text retained. Versioned rate estimate:
**US$0.0291295 total**, **US$3.6411875/1,000 completed model replies**; cap respected.

| Diagnostic (8 samples; linear-interpolated percentile) | p50 | p95 | max |
| --- | --- | --- | --- |
| Model HTTP request | 4.120s | 7.406s | 8.741s |
| Local application until reply persisted | 4.165s | 7.452s | 8.789s |

One sample exceeded 8 seconds; no existing latency requirement was changed or
waived. This small local population does not establish real WhatsApp latency.
The adapter's persisted round-trip metric also includes bounded client/parse
cleanup; the table measures the HTTP request separately through smoke instrumentation.

Restarting the app with the same SQLite preserved both handoffs and both intake
states. Replaying the human-request Message added no generation/delivery; a new
Message during that handoff was persisted as suppressed without reply/outbox.
Eight accepted fake deliveries remained accepted, no extra OpenAI/fake sends,
zero pending generation work. Readiness passed before and after restart.

Offline: **1044 tests passed (30 added)**, Ruff check/format, compileall, pip check,
and diff checks passed. Standards and Spec code-review axes found no material
findings; runtime architecture, safety and config/secrets checks passed. The
cache-write accounting contract was verified against official Responses docs
and previous live evidence; missing required usage remains fail-closed.

Intelligence: validated enough, frozen. Runtime: validated locally.
WhatsApp production-ready: **NO**. Ticket 12 stays **in-progress**; real messaging/
Meta integration and operational readiness remain separate gates. Historical
intelligence populations and their gate results were not rescored or altered.
