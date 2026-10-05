# V1 messaging integration preflight

Approved scope: product-owner requests of 2026-10-05. Offline transport validation;
no messaging API calls, new paid LLM calls, customer data or credential changes.

## Integration baseline

Runtime branch `codex/v1-openai-runtime-promotion` was published at
`13ecbf70cb8609fd8f5ce6467e3316639d3606a4`, derived from integration baseline
`97fe5f05e8b9584e287c7d7e26df692f8cd445f3` with commits `b457ec5` and `13ecbf7`.
[PR #1](https://github.com/zazacknazzo/rj-studio-ai/pull/1) merged into
`codex/v1-conversational-polish` at
`205b5b00a0e8586f9f066ca782a3ca7074480686`; local and remote matched.
No merge to main. Preflight branch: `codex/v1-messaging-integration-preflight`.

V1 intelligence = **VALIDATED ENOUGH**; Agentic Surface = **APPROVED / FROZEN**.
OpenAI Low runtime = **MERGED / VALIDATED LOCALLY**; messaging = **NEXT GATE**.
The safe default remains fixed. Explicit runtime selection is described in
[runtime promotion](v1-openai-runtime-promotion.md); this audit did not modify
the local `.env` or activate OpenAI/proactive operation.

## Current architecture

```text
Signed provider webhook → provider-neutral events → atomic SQLite ingress → ACK
SQLite polling → Processing Executor → configured OpenAI Low generator
→ untrusted decision → trusted finalizer / action and handoff authorization
→ atomic AIReply + OutboundDelivery + processing completion
SQLite polling → Outbound Executor → provider REST adapter → ProviderAcceptance
Signed status webhook → durable evidence → monotonic delivery state
```

`main.py` selects one provider and filters outbound acquisitions by that provider.
Processing polls pending generations across providers; it is not provider-filtered.
Therefore a smoke must use an isolated database, never an existing backlog.
Twilio proactive ACK is empty TwiML; Meta ACK is empty plain text. Neither ACK
is assistant speech. Legacy TwiML is a separate rollback mode, with no proactive
executor and a database safety check; do not switch modes with unresolved work.

Ingress persisted, generation completed, provider accepted, sent, delivered,
read and failed are distinct observations. Generation does not prove delivery.
Acceptance releases the ordering barrier and permits approved assistant context;
it does not prove sent/delivered/read. Unknown/unrecognized callback statuses
are acknowledged without inventing success or scheduling a retry. A delivery
whose submission outcome is `unknown` is a different concept: it remains durable
and ineligible for automatic resend, including after restart/lease expiry.

Owner tokens, short SQLite transactions, unique inbound/reply/delivery constraints,
durable polling, monotonic callbacks and pending pre-correlation status evidence
remain unchanged. Failed/ambiguous delivery remains operationally visible. See
[architecture](../ARCHITECTURE.md) and ADR 0006 for the existing lifecycle.

## Provider contracts audited

| Boundary | Twilio | Meta |
| --- | --- | --- |
| Inbound | Form POST `/webhooks/twilio`; canonical From/To/Body/MessageSid | JSON POST `/webhooks/meta`; text events and phone-number metadata |
| Authentication | RequestValidator against configured public URL and Auth Token | Raw-body SHA256 HMAC with App Secret; GET challenge requires verify token |
| Outbound | Messages resource create through SDK with zero transport retries | Versioned Graph `/{phone-number-id}/messages` text POST |
| Acceptance | Valid SM/MM MessageSid; initial queued is sufficient | Valid wamid in successful create response |
| Status | Separate signed `/webhooks/twilio/status`; sent/delivered/read/failed; undelivered maps failed | Signed `/webhooks/meta`; sent/delivered/read/failed |
| Eligibility | Sandbox/channel enrollment is an external operational requirement | Recent durable inbound for matching Customer/channel, strictly inside 24-hour free-form window |
| Retryable mapping | Explicit HTTP 429 only | HTTP 429 or explicit transient rejection flag, per existing M06 contract |
| Permanent mapping | Known rejection code allowlist | Explicit non-transient rejection or 401/403, per existing M06 contract |
| Ambiguity | Timeout/network, unclassified API error, malformed acceptance → unknown | Timeout/network, malformed acceptance, unclassified API error → unknown |

Core retryable submissions use persisted `next_attempt_at`, bounded attempts
(default 3), exponential backoff (default 1–30s). No retry of unknown/failed or
accepted delivery. No transaction stays open during the HTTP call. Network
submission followed by lost local acceptance commit remains ambiguous; the
expired sending claim becomes unknown, never an assumed safe resend.

Twilio sender is the canonical inbound To/channel, not a `TWILIO_WHATSAPP_FROM`
setting. Meta has no WABA ID setting: WABA/app webhook subscription, phone-number
ownership, token permissions and sender eligibility are external setup checks.
Local `is_configured()` validates syntax/presence, not provider authorization.

## Local configuration checklist — presence only

Audit date: 2026-10-05. No values were printed or persisted. No external overrides
were found for the audited keys. Statuses describe this workstation, not GitHub
or deployed credentials. PRESENT does not prove validity, permissions or rotation.

| Config | Status | Operational qualification |
| --- | --- | --- |
| OPENAI_API_KEY | PRESENT | Existing local runtime smoke evidence; no new call |
| LLM_PROVIDER | PRESENT | Current local selection is not OpenAI Low |
| WHATSAPP_PROVIDER / DELIVERY_MODE | PRESENT | Current local selection is not Meta proactive |
| TWILIO_ACCOUNT_SID | PRESENT | Correct account association still needs operator confirmation |
| TWILIO_AUTH_TOKEN | UNTRUSTED/ROTATION_REQUIRED | Nonempty; no safe evidence of rotation after possible exposure |
| TWILIO_API_KEY_SID / TWILIO_API_KEY_SECRET | PRESENT | Trust, account association and permissions unproven |
| TWILIO_VALIDATE_SIGNATURE | PRESENT | Enabled locally; must stay enabled |
| TWILIO_PUBLIC_WEBHOOK_URL / TWILIO_STATUS_CALLBACK_URL | PRESENT | Public TLS and provider alignment not verified in this round |
| TWILIO_WHATSAPP_FROM | NOT_APPLICABLE | Sender comes from canonical channel |
| META_WHATSAPP_ACCESS_TOKEN | UNTRUSTED/ROTATION_REQUIRED | Nonempty; rotation/trust unproven |
| META_WHATSAPP_PHONE_NUMBER_ID / META_WHATSAPP_API_VERSION | PRESENT | Ownership, version availability and sender eligibility unverified |
| META_WHATSAPP_APP_SECRET | MISSING | Local key exists but is empty |
| META_WHATSAPP_VERIFY_TOKEN | PRESENT | No value shown |
| WABA ID config | NOT_APPLICABLE | Not a Settings field; subscription must be checked externally |
| ALLOW_LIVE_MESSAGING_SMOKE | MISSING | Live opt-in must remain off in this round |
| TEST_WHATSAPP_RECIPIENT | MISSING | Never infer a recipient from persisted data |

**TWILIO_LIVE_SMOKE_BLOCKED_PENDING_TOKEN_ROTATION**.
**META_LIVE_SMOKE = BLOCKED**: missing App Secret and unproven access-token trust.
Previous Brazil restriction and production-number eligibility are unresolved
operational evidence, not assumed resolved or newly reproduced.

Do not dump Settings, provider objects, raw requests, auth headers or provider
errors. OpenAI key is excluded from Settings representation/serialization;
older messaging credential fields are not generally redacted by Settings itself.
Treat raw Settings repr/model_dump as sensitive and prohibit them in smoke logs.
This is a remaining production hardening concern, not evidence of a leak here.

## Offline evidence

`tests/test_messaging_integration_preflight.py` adds 12 network-blocked cases:
both real ingress adapters with valid/invalid signatures, duplicate inbound,
real Processing/Outbound Executors, controlled OpenAI HTTP response and usage,
synthetic approved Knowledge, trusted price rendering, actual sender adapters
with controlled SDK/HTTP boundaries, signed callbacks and SQLite state.

Eight cases exercise sent/delivered/read/failed, duplicate and out-of-order
callbacks, restart and replay without a second generation/submission. Two cases
exercise ambiguous transport failure → unknown, restart and no resend. Two
exercise early signed status evidence, restart before correlation and subsequent
acceptance reconciliation. The proposed untrusted price cannot change the trusted
fixture price. Fixtures are exclusively synthetic, not Salon Knowledge changes.

Existing tests cover challenge success/failure, invalid payloads, ignored statuses,
service-window refusal, provider errors/timeouts, bounded retries, database
constraints and atomic rollback, concurrent claims, provider filtering, handoff
and intake fences, generation deadlines and migration/restart preservation.
No prompt, oracle, generation configuration or production behavior was changed.
First-instruction checks: **1056 tests passed**, Ruff check and format check,
compileall, pip check and diff check passed. Standards review found no material
issues; Spec review corrected the audit wording about outbound-only filtering.

## Next live smoke procedure — prepare only

Recommendation: **BOTH BLOCKED**. Prefer Meta as the development target only after
all its gates below pass; this is not META READY FIRST. Twilio remains an alternative
only after documented rotation, permissions and Sandbox setup pass.

1. Obtain trusted credentials privately: Meta App Secret and confirmed rotated
   access token, or confirmed rotated Twilio Auth Token plus trusted API key.
   Confirm the selected app/account, test sender and explicit operator-controlled
   test recipient. For Meta, resolve Brazil eligibility and WABA subscription.
2. Obtain explicit next-round authorization. Require
   `ALLOW_LIVE_MESSAGING_SMOKE=1` and `TEST_WHATSAPP_RECIPIENT` supplied privately
   as the operator's test E.164 number. Missing flag/recipient must stop before
   app lifespan/executor startup. These are smoke controls, not currently Settings
   fields; adding them to `.env` alone does not fence the existing runtime.
3. Use a smoke-only sender wrapper enforcing that recipient and one submission
   maximum. A fresh isolated persistent SQLite volume must contain no customer
   records or pending production work. Never point the smoke at the normal DB.
   Inject the guarded sender before starting the app; do not run a default
   unguarded Uvicorn composition for smoke. No fallback to salon/last customer.
4. Select `LLM_PROVIDER=openai`, approved Low/1024 defaults, selected
   `WHATSAPP_PROVIDER` and `DELIVERY_MODE=proactive` in the isolated smoke process.
   Sender is the official Meta test phone-number ID or Twilio Sandbox channel;
   no production-number onboarding. Preserve signatures and bounded deadlines.
5. Verify local health/readiness and external HTTPS with normal certificate
   validation; align Meta GET/POST callback or Twilio inbound/status callback
   with that public URL. No TLS bypass. Enroll only the test recipient as required.
6. Operator sends exactly one synthetic inbound: “Oi, quero informações sobre
   um corte.” Observe durable admission before ACK, one completed generation,
   one AIReply/outbox, one real submission, valid provider ID and accepted state.
   Verify empty ACK and no TwiML + REST duplicate. No booking or availability claim.
7. Observe signed status: sent → delivered → read when available. Absence of read
   is not failure; missing delivery evidence must be reported as pending, not
   invented. Accept duplicate/out-of-order events without regression. Record date,
   revision, checks, states, safe error codes and sanitized timing; never content
   dumps, phone numbers, credential values, raw provider payloads or full IDs.
8. Stop on unexpected recipient, duplicate send, signature/config failure,
   unsafe factual/action result, unknown outcome, provider rejection or accounting/
   privacy error. Do not automatically resend unknown or restart for another send.
   Shut down acquisition/executors; preserve DB evidence privately. Disable smoke
   opt-in and remove temporary callback configuration manually if needed. Do not
   switch to legacy as an emergency resend; reconcile ambiguous work explicitly.

No live smoke is authorized or executed by this preflight. Real public TLS,
credentials, channel delivery and WhatsApp latency remain unvalidated. Intelligence
is frozen and Ticket 12 remains in-progress. WhatsApp production-ready: **NO**.
