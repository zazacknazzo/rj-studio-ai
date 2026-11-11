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
The persisted cutoff never decreases, including with a backwards local clock
correction and interleaved echoes. Revisions serialize decisions; timestamps do
not establish external event order. Incorrect but plausible remote timestamps
cannot be perfectly detected, so reliable clocks remain a deployment requirement.
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

Example payload for either POST (synthetic operation identifier):

```json
{"operation_id":"0123456789abcdef0123456789abcdef","expected_revision":1}
```

Example response (synthetic Conversation identifier):

```json
{"conversation_id":"abcdef0123456789abcdef0123456789","paused":false,"revision":2,"handoff_active":true,"in_flight_possible":false,"unresolved_delivery":false}
```

This response still reports an active policy handoff. Its existing trusted local
release operation remains separate; the API never exposes or accepts episode tokens.
No general `automation_active` promise is made: future inbound admission, ordering,
handoff, delivery and provider eligibility remain separate gates. The journal's
channel lifecycle observations are not an implemented channel gate yet (Ticket 09).

## Telnyx offline ingress evidence (Ticket 07)

The dormant Message adapter now supplies source timestamps and preserves Message,
event and Meta alias identities separately. It is not selected by configuration and
has no external route. Telnyx ingress credentials alone still cannot enable delivery.

For a future authorized deployment, the operator procedure must be usable before
manual replies: select the intended Conversation through a trusted client, GET its
current revision, POST pause with the dedicated Bearer and operation identifier,
then confirm the durable paused state and inspect in_flight_possible. If the pause
fails or identity is unresolved, do not assume takeover protection. Absence of echo
never confirms that automation is paused. The mobile selection/client/deployment
workflow remains CX-07/CX-08 and requires a separate release gate.

An unseen delayed echo can pause again after resume. Fetch current state and assess
new manual activity before another explicit resume; do not automatically resume on
a timer or discard the event based on its timestamp. A known logical echo replay
keeps its original applied effect and does not repause. Clock correction never lowers
the local cutoff. Validate NTP and real timestamp provenance before pilot; future or
unproven inbound is suppressed after resume, including once the clock catches up.

Unsupported inbound media/location/files and unknown events currently receive no
successful ACK. Status/lifecycle await Tickets 08/09. Before enabling Ticket 12's
route, define durable handling and operational visibility for unsupported formats,
verify profile subscriptions, raw duplicate-header rejection and streaming limits.
No unsupported event may be silently discarded under a 2xx response. Ticket 07's
local multi-envelope test interface does not assert Telnyx sends HTTP batches.
