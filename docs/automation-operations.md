# V1 operational API

Private routes, intended for a future mobile client over HTTPS:

- GET `/admin/conversations/{id}/automation`
- POST `/admin/conversations/{id}/automation/pause`
- POST `/admin/conversations/{id}/automation/resume`

`id` is an opaque 32-character lowercase hexadecimal identifier, not a phone,
provider ID or episode token. A trusted local integration can obtain it via
`store.automation_identifier(inbound_message_id)`; there is no public enumeration.
POST accepts exactly `operation_id` (a fresh UUID.hex, 32 lowercase hex characters)
and `expected_revision` (integer >=0). Reuse the same operation_id and payload when
retrying a lost response; a new intent requires a new key. CAS conflicts require a
fresh GET and human decision, never an automatic resume retry with a new revision.

Responses: conversation_id, paused, revision, handoff_active, in_flight_possible,
unresolved_delivery. `paused=false` only clears operational pause; it does not mean
handoff or delivery blockers are clear or that an old Message will be processed.
Replay returns the original snapshot, so GET again for current state. Errors:
401 missing/invalid Bearer; 403 permission/resource denied; 404 absent resource or
action; 409 stale revision, operation-key conflict or unresolved channel identity;
422 invalid payload; 413 body >1024 bytes; 503 unavailable configuration/storage.
No response contains Message content, customer phone, provider identifier or token.

## Configuration and rotation

No credentials are supplied by the repository. Provision a cryptographically random
Bearer secret with at least 256 bits of entropy through the deployment secret store.
Do not use a password, provider key, owner token or episode token. Configure:

- OPERATOR_SECRET_SHA256: lowercase SHA256 hex digest of that Bearer secret.
- OPERATOR_ID: opaque nonpersonal label, 1–64 ASCII letters/digits/underscore/hyphen.
- OPERATOR_PERMISSIONS: JSON array of `read` and/or `control`.
- OPERATOR_CONVERSATIONS: JSON array of opaque IDs; explicit `*` grants all resources
  of this single-business V1. Empty/invalid values disable administrative routes.

Send the secret only in `Authorization: Bearer …`, never a URL or query string.
Protect both service and proxy access with HTTPS, restrict administrative ingress,
and disable/redact Authorization headers and request-body capture in proxy/APM logs.
The application uses no cookies, query credentials or browser credential storage.
A mobile client must use platform secure storage. Public internet exposure without
TLS and access controls is unsupported. Digest is excluded from Settings repr/dumps.

Rotation: provision a new random secret and digest, distribute via secure channels,
replace only the operator secret configuration and restart the application. The old
credential immediately fails on the restarted process. Keep the same operator ID
for receipt retries; changing operator identity intentionally conflicts with old
keys. No overlap or second credential is introduced. No commercial credentials need
changing. These are deployment instructions; no credentials were provisioned here.

## Resume and delayed events

Only new eligible Messages with reliable origin time after resume can generate.
Missing/old/future/contradictory timestamps are suppressed permanently. Legacy
Meta/Twilio messages lacking that provenance after resume will also be suppressed;
this ticket does not invent timestamps or enable an adapter. Known echoes stay
deduped; unknown delayed/new human Messages repause conservatively. Do not infer
chronology from event IDs, aliases or arrival order. Prompt/context never receives
manual Message content. No guarantee of complete echo history or perfect ordering.

Unknown is never resent. Sending already authorized can escape pause in the gap
before HTTP; in_flight_possible reports that evidence. Resume cannot recall it,
release handoff, revive cancelled/suppressed work or erase audit evidence. Journal,
controls and receipts remain held without purge; retention remains a release blocker.
