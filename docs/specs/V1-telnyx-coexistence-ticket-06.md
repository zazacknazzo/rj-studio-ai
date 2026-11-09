# Coexistence Ticket 06 — configuration and webhook authentication

Status: approved

Explicit user authorization on 2026-11-09: Ticket 06 only, from
`codex/telnyx-coexistence-05-admin`, commit
`7d597acc20bda937b708c53ef2fa54427fec5109`. Tickets 01–05 are approved.
Tickets 07–13, live integration, number registration, commercial credentials,
paid calls, sending and merging main are not authorized. Normal push of this
isolated branch is authorized after independent Standards/Spec review and secret
audit. Ticket 07 must wait for the user's direct GitHub audit and authorization.

This records the authorized slice of the 2026-10-31 Telnyx Coexistence plan. The
original Ticket 06 requires raw-byte Ed25519 verification, a pinned verifier,
expected scope, body limits, temporal replay protection, safe configuration and
no production runtime enablement. The current request explicitly excludes
semantic inbound/echo, status and lifecycle parsing. Scope inspection below is
only authorization; it creates no canonical event and infers no business state.

## Boundary and configuration

`TelnyxWebhookAuthenticator(Settings, clock=...)` is the ingress portion of the
future adapter. It is deliberately not yet an `InboundWebhookAdapter`: no
`receive`, successful ACK, empty canonical batch, sender, route or factory is
introduced. `authenticate(ProviderWebhookRequest)` returns the exact original
bytes after authentication and scope validation. This result is not permission
to persist a Message, run the LLM, update a channel or return an HTTP success.
Tickets 07–09 own semantic parsing and atomic effects; Ticket 12 owns composition.

Construction requires proactive mode, a strict Base64 raw 32-byte Ed25519 public
key, a business E.164 number, and nonempty profile, organization and WABA IDs.
IDs are bounded opaque ASCII tokens, not inferred from message fields. The public
key must come from trusted deployment configuration; neither request headers nor
payloads can supply a replacement. No API key is needed for verification and no
outbound credential is introduced. Administrative Bearer authentication stays
unchanged and grants no webhook authority.

Settings redact the key and scope identifiers from repr/dumps and validation
inputs. Configuration errors use a fixed message without values. Construction
snapshots the validated ingress values; reconfiguration requires a new instance.
No signature-disable switch exists. `WHATSAPP_PROVIDER` still accepts only Meta
and Twilio; both Telnyx+legacy and Telnyx+proactive runtime selections are rejected.
A complete ingress configuration is never treated as sending readiness.

Body limit defaults to 262,144 bytes, configurable from 1 to 1,048,576. The future
HTTP composition must enforce the same limit while streaming, before buffering;
this existing provider-neutral request already contains buffered bytes. The
signature window defaults to 300 seconds, configurable from 1 to 300. These are
local conservative implementation choices, not claims about provider delivery SLAs.

## Authentication and scope

- Require POST, JSON media type and a nonempty bytes body within the size limit.
- Resolve authentication headers case-insensitively, reject duplicates observable
  in the request map and comma-joined values. The future HTTP route must reject
  duplicate raw headers before converting them to a dictionary.
- Require an ASCII decimal Unix-seconds timestamp of at most 12 digits. Preserve
  its original text for signing. Accept absolute clock difference <= tolerance;
  reject expired, too-far-future, missing, malformed and non-finite clock values.
- Verify Ed25519 over `timestamp.encode('ascii') + b'|' + original_body`, using
  strict canonical Base64 and a 64-byte signature. Library: `cryptography==50.0.2`.
- Only after successful verification, inspect UTF-8 JSON and scope. Reject
  malformed envelopes, duplicate JSON keys, nonstandard constants and excessive
  nesting with generic errors. Never log request bodies, headers, signatures,
  credentials, phone numbers, content or external identifiers.
- For `message.received`, scope is the inbound business `to` number. For
  `message.echo`, `message.sent`, `message.finalized` and `message.read`, it is
  outbound `from.phone_number`. Require WHATSAPP, matching direction, profile
  and organization. If WABA is present it must also match. Do not inspect text,
  message origin, status recipients, Message IDs, timestamps or echo content.
- `whatsapp.account.update` requires the configured WABA and account record type,
  without requiring absent Message/channel fields. Other scope fields, if
  present, must match. Lifecycle transition values are not interpreted.
- Unknown contracts, including the redundant `whatsapp.messages` route, fail
  closed until a reviewed scope rule exists. No silent success is returned.

A current signature can carry an old `occurred_at`. Repeated requests inside the
cryptographic window remain valid; authentication is stateless and implements no
deduplication. Durable deduplication and business chronology retain their separate
approved contracts. No active-channel, LLM, sender or store dependency exists in
this layer, so a later operational ingress can use it while sending is blocked.
This ticket alone does not provide that end-to-end ingress.

## Verification and limits

Synthetic Ed25519 keys and signed original bytes cover whitespace/Unicode,
mutation, wrong keys, missing/malformed signatures, timestamp tampering, both
window boundaries, expired/future/invalid timestamps, repeated events, fresh
signatures over old events, missing/invalid configuration, wrong or missing scope,
body limits, parsing after crypto, error/log redaction, no dormant HTTP route and
no database effects. Full existing regressions protect Tickets 01–05, Meta,
Twilio, outbox, pause/resume and frozen intelligence. Run with sanitized environment,
no commercial .env and IP network disabled, including child Python processes.
Run full pytest, Ruff, compilation, diff checks and independent reviews before push.

Residual limits: no real signature or eligibility validation; trusted public-key
provisioning and synchronized clocks are deployment requirements. In-window replay
is intentionally possible and must meet durable deduplication downstream. Raw HTTP
stream limits/duplicate-header handling, durable ACK, semantic event validation,
channel gates and sending are future work. Existing unbounded operational retention,
echo best-effort and the marker-to-HTTP race remain unchanged release blockers/limits.

## Official sources checked 2026-11-09

- [Webhook fundamentals](https://developers.telnyx.com/docs/development/api-fundamentals/webhooks/receiving-webhooks): exact raw bytes and product-specific signature contracts.
- [Messaging signature contract](https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks): Ed25519, Base64, timestamp-pipe-body and five-minute replay guidance. Its JSON-reserializing example is not used.
- [Coexistence webhooks](https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks): message/echo scope, organization/profile fields, WABA lifecycle envelope and redundant WABA messages route.
- [PyCA Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/): raw public-key import and signature verification.
- [Pinned package](https://pypi.org/project/cryptography/50.0.2/): version selected for reproducible verifier behavior.
