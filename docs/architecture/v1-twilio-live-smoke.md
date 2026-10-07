# First V1 Twilio live transport smoke

Approved scope: product-owner request, 2026-10-07. Intelligence/Agentic Surface,
prompt, oracle, persona, grounding, handoff and appointment behavior remain frozen.
Baseline: `8b6e76399a551868348382863f335402c29782e4`, published to
`origin/codex/v1-messaging-integration-preflight`; integration base remains
`205b5b00a0e8586f9f066ca782a3ca7074480686`. No merge to main.

## Current result

**BLOCKED_PENDING_TOKEN_ROTATION**. No real submission or provider API call.
Local credentials are present; Account/API key SID formats and Auth Token format
pass local checks. That is not evidence of rotation, validity, account association
or permissions. Operator rotation attestation, smoke sender, test recipient,
isolated database path and live opt-in are absent. No local credential was changed
and no rotation/opt-in was invented. Public TLS/routing is **NOT TESTED**.

Meta remains **BLOCKED_PENDING_APP_SECRET_AND_CREDENTIAL_TRUST**; App Secret is
missing, token trust unproven, and previous Brazil/sender eligibility unresolved.
No Meta validation or Anthropic call is part of this smoke.

## Secret redaction

`Settings` excludes OpenAI/Anthropic keys, Twilio account/key identifiers and
credentials, Meta access/App/verify secrets from repr and serialization. Values
remain ordinary strings available internally to existing adapters. Nonsecret
provider/model/configuration fields remain inspectable. Validation preserves
field/type/constraint diagnostics but removes supplied inputs from the raised
ValidationError, including `errors()` and `json()`, not merely its string form.
Never print `__dict__`, raw source environments, exception contexts or HTTP payloads.

The smoke SDK client has a silent wire logger and zero transport retries. CLI
suppresses noisy network/access logs, catches errors without arbitrary exception
text and emits allowlisted metadata only. No settings or credential values are
written to its report. This does not sanitize arbitrary third-party code that
explicitly logs internal credential values; existing code must keep that rule.

## Preconditions and private controls

Normal credentials keep their existing names: `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`,
`TWILIO_PUBLIC_WEBHOOK_URL`, `TWILIO_STATUS_CALLBACK_URL` and enabled
`TWILIO_VALIDATE_SIGNATURE`. The real sender adapter's configuration is checked
**before** constructing the smoke guard or starting the callback server.

Smoke-only controls, loaded privately from local environment/file:

| Control | Requirement |
| --- | --- |
| TWILIO_AUTH_TOKEN_TRUST | Exactly `rotated`, only after actual operator rotation of the configured Auth Token |
| TWILIO_SMOKE_SENDER | Explicit E.164 Sandbox sender; no inferred/runtime default |
| TEST_WHATSAPP_RECIPIENT | Explicit E.164 operator/team-controlled test number, different from sender |
| TWILIO_SMOKE_DATABASE_PATH | Fresh `work/twilio-live-smoke/<run>/smoke-live-messaging.db`, never normal DB |
| ALLOW_LIVE_MESSAGING_SMOKE | Exactly `1` plus CLI `--execute`; default invocation is check-only |

These controls are not normal Settings fields. The trust marker is an operational
attestation, not a cryptographic or online verification. Never write it based on
presence/format alone; never compare, print or automatically rotate the token.
The operator must verify account association, API-key trust/permissions, Sandbox
sender and recipient enrollment. Do not use a Customer or salon number as fallback.

Both callback URLs must use HTTPS, the same host, no credentials/query/fragment,
and exact paths `/webhooks/twilio` and `/webhooks/twilio/status`. No TLS bypass.
The smoke sidecar accepts **status callbacks only**, not inbound Messages; this
first gate is outbound-only. It cannot generate a second response from inbound.

## Driver and durable safety

`python -m rj_studio_ai.twilio_live_smoke --check` is read-only and network-free.
Missing trust returns BLOCKED_PENDING_TOKEN_ROTATION; otherwise missing config
blocks; valid config without opt-in reports READY_FOR_LIVE_SMOKE /
AWAITING_OPERATOR_OPT_IN. A ready check is not public TLS proof or live success.

Execution reserves the explicit isolated DB with exclusive creation, permissions
0600, applies existing migrations and verifies SQLite durability. Existing files,
normal DB, symlinks and paths outside the smoke directory are rejected. The DB is
initially empty. An existing reservation is never reused, even if startup failed:
another instance/restart cannot silently resume submission. Preserve evidence.

The driver uses the existing `LiveSmokeOutboundSender`: exact recipient, no
fallback and one reservation before delegation. It creates a **synthetic local**
Message/claim and completes one synthetic AIReply + pending delivery atomically
using the existing persistence API. That synthetic Message is not evidence of a
real Twilio inbound webhook or a generated model reply. Body: “Teste RJ Studio AI”.
Then it invokes the existing OutboundDeliveryRunner **once**, maximum attempts 1.
No processing/outbound polling executor and no OpenAI generation is started.
The approved OpenAI/Low/1024 candidate is preserved, not changed or rerun.

Provider acceptance remains a valid MessageSid from create (initial queued is
valid). Signed callbacks reuse TwilioProvider and durable status persistence;
early evidence is buffered/reconciled, duplicate/reordered statuses are monotonic,
and unrecognized statuses cannot schedule a send. Only normalized evidence is
persisted, never raw provider payloads. Invalid callbacks stop the smoke.

Timeout/ambiguous response remains unknown; expired sending and lost local
acceptance commit are also conservatively ambiguous. Acceptance is null/unknown
in the report when local evidence cannot prove it. There is no automatic retry,
not even after 429. A proven retryable error exhausts this smoke's one-attempt
budget and becomes failed under the existing runner policy. Do not change paths,
recreate the guard or switch to TwiML to bypass a stopped/unknown submission.
Once external submission started it cannot be presumed cancelled.

## Exact next procedure — not executed

1. Operator rotates the Twilio Auth Token privately, updates the local token and
   only then records `TWILIO_AUTH_TOKEN_TRUST=rotated`. Confirm trusted dedicated
   API key/account, explicit Sandbox sender and enrolled operator test recipient.
2. Supply the remaining private smoke controls, leaving live opt-in off. Choose
   a new explicit isolated path. Run the network-free check and correct blockers.
   Never commit `.env`, phone numbers, DB or local reports.
3. Prepare HTTPS forwarding to `http://127.0.0.1:8001`, matching the private public
   URL fields. The driver owns its status-only sidecar on this port; do not point
   the tunnel at the normal app. Outbound create supplies StatusCallback itself.
   No inbound Sandbox webhook change is needed for this outbound-only gate.
4. Only with explicit operator opt-in set to `1`, execute:

   ```bash
   .venv/bin/python -m rj_studio_ai.twilio_live_smoke --execute
   ```

   Startup is bounded to 5s, local readiness is checked, and public `/health` must
   return this run's unique smoke ID through normally validated TLS (3s connect /
   5s read, no redirects). Another app's HTTP 200 is insufficient. No Twilio POST
   occurs until these checks pass. Do not run the normal unguarded app for smoke.
5. Observe exactly one adapter submission and local provider ID/acceptance. Default
   callback observation is 30s (configurable up to 60s), no retry. Acceptance with
   missing callback is `accepted_callback_pending`, an incomplete/failed live gate,
   never delivered. Failed/invalid callback or ambiguous outcome stops observation.
   Sent/delivered/read remain distinct; read is not mandatory.
6. Preserve the private DB and allowlisted `result.json` (0600), timestamp, smoke
   ID, hashed provider ID, result class, state, callback/duplicate counts, zero
   retries and observed submission round trip. Submission count is the local
   adapter-attempt count, not proof of HTTP byte delivery when outcome is unknown.
   A process crash can prevent report creation; the DB reservation still prevents
   automatic rerun. Inspect locally without printing PII/full IDs/secrets.
7. Shut down the callback server and disable opt-in. Remove temporary infrastructure
   when finished. Never retry or reuse this DB as production data. Callback failure
   after a real acceptance does not erase acceptance or cancel provider responsibility.

PASS requires one submission, durable acceptance/provider ID, at least one
correlated signed callback processed correctly, consistent state, zero retries,
zero duplicate sends and no exposure. This proves outbound transport only; a later
real inbound/OpenAI integration and operational gate remain required.

## Validation and reviews

Offline tests exercise repr/dumps/validation/startup logs, internal credential
access, missing trust/flag/config, explicit recipient, sender separation, DB
isolation/exclusive creation, HTTPS route proof, one manual submission, callback
authentication/early correlation/monotonicity, failures, restart and lost acceptance
commit. All provider network boundaries are mocked. Full checks and independent
review outcomes are recorded after completion below.

V1 intelligence: VALIDATED ENOUGH; Agentic Surface: FROZEN; OpenAI Low runtime:
VALIDATED LOCALLY; offline messaging preflight: PASS. Twilio live: **BLOCKED_PENDING_TOKEN_ROTATION**. WhatsApp production-ready: **NO**. Ticket 12 remains in-progress.
