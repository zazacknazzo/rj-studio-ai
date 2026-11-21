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

## Ticket 08: contradictory delivery evidence (offline)

Telnyx failure plus delivered/read is shown by `list-blocked-deliveries` with reason
`provider_status_conflict`, retaining state delivered/read. The authenticated state
reports `unresolved_delivery=true`. This is a durable block for subsequent ordered
processing/submission, even after pause/resume or restart. Do not retry or create a
replacement delivery to clear it. Ticket 08 adds no conflict-resolution command;
future recovery requires an explicitly approved policy. Unknown/unconfirmed provider
observations likewise never justify retry. The status ledger retains private routing
IDs under CX-01; it stores no message text or raw provider errors. Existing purge and
Conversation deletion reject unresolved conflicts instead of hiding them.

## Offline account lifecycle

Ticket 09 binds the configured Telnyx WABA explicitly to the business number,
organization and profile. It rejects configuration rebinding. Account events do
not identify a Customer or create Conversations. Offboarding/partner removal
block the channel; reconnect requires verification. Missing channel verification
also blocks Telnyx generation and submission. No command in this release enables
or reconnects that channel. Conversation pause/resume and handoff release remain
independent and cannot override it. Unknown lifecycle transitions reject without
ACK and require future ingress policy; do not bypass validation to stop retries.

Observations and applied effects survive restart and Message maintenance. Their
retention remains a release blocker. Already authorized HTTP/LLM work may finish;
LLM output cannot commit after a lifecycle block, while submission results remain
evidence. Never resubmit old work or erase markers/attempts to clear this gate.
Future operational verification, activation and rebinding require their own
specification, authorization, audit and tests. See ADR 0017 and issue #11/CX-33.
# Ticket 10: offline eligibility evidence

Telnyx delivery authorization now also requires a proven Customer service window,
explicit consent and unchanged submission identity/payload. Exactly 24 hours is
outside the local free-form policy. Missing evidence, an unhandled recipient
identity, a backward local clock, a blocking handoff or unresolved outcome denies.
Pausing/resuming a Conversation does not refresh the window, grant consent,
activate a channel or make an unknown delivery retryable.

The new consent rows and template evidence objects are trusted internal contracts,
exercised with synthetic fixtures only. There is no operational permission to
populate them manually for a real Customer, verify templates, enable a channel or
send messages in this ticket. Collection, revocation, freshness and authenticated
operational verification require a subsequent reviewed workflow. Evidence references,
phone/BSUID identifiers, submission keys and fingerprints are private operational
metadata; do not copy them or message content into logs or public issues.

On timeout or restart after possible submission, preserve `unknown` and investigate
through a future authorized reconciliation workflow. Never generate a replacement
key or replay merely because the provider documents an idempotency window. Its
retention is bounded, and current local code does not prove future HTTP bytes or
remote processing. The authorization-to-HTTP and query-to-LLM residual windows
remain; this ticket neither performs HTTP nor promises recall.


## Ticket11 offline sender and mandatory restore gate

The text sender exists only as an uncomposed component with an injected intercepted
exchange. No Telnyx runtime selector, outgoing worker, credential loading or public route
has been enabled. Its presence is not activation authority. HTTP acceptance is distinct
from sent/delivered/read. Unknown,409/10036,422/10027,429/5xx and timeout do not authorize
resubmission or replacement keys. A Telnyx runner/executor selects only Telnyx work.

AUD01 remains an operational blocker: opening a structurally valid old backup can lose
later submission or disconnect barriers. Before any future approved operational restore,
quarantine must disable all egress outside the restored file; independent inventory and
reconciliation of possible submissions, channel/sync, consent/window and authenticated
release must precede worker composition. These are required future capabilities, not
commands implemented here. Never recover by clearing unknown, deleting markers or
creating a new submission key. Additional DB fields/MACs alone do not fix stale restore.

Request MAC receipts survive terminal content purge and have no automatic expiry;
CX01 retention/erasure policy remains required. Integrity keys must be held separately
and stable; do not publish them or use commercial credentials during offline checks.
The [Ticket11 report](architecture/v1-ticket11-validation.md) distinguishes reproduced
restore failures, passing offline regressions and operational protection still absent.

## Ticket12 offline HTTP diagnostics and quarantine

The synthetic `create_telnyx_offline_app` factory is for ASGI tests only; it is not
mounted on the commercial app and has no sender, workers or release command. Do not
serve it as a workaround for the disabled production provider. `/health` indicates
process responsiveness. `/ready` separates ingress, persistence, administration,
generation, egress and operational channel; HTTP200 from this local diagnostic never
grants channel authority. `/metrics` contains finite process response/latency buckets.

A422 means an authenticated envelope/contract could not be handled. No supported
Message/effect was acknowledged or silently skipped. SQLite keeps only aggregate
`telnyx_ingress_rejections(reason, observations, first_seen_at, last_seen_at)`; inspect
with a local read-only SQLite connection. Counts include retries and contain no content
or routing identifiers; they cannot recover the unsupported Message. A503 means retry
is necessary because persistence, capacity or deadline did not permit a timely durable
acknowledgement. A commit may already be durable; replay the same provider event, not
new identities. Rejection observations themselves can fail503 and process metrics show
that failure. Restart preserves durable counters but resets process metrics.

Before a future explicitly authorized deployment, define monitored alerts and operator
handling for422/503, validate actual provider retry/failover and subscription settings,
provision key/clock/TLS safely, and establish privacy/retention policy. Media inbound and
future schemas are unsupported; echo media remains a content-free human pause signal.
Do not ACK unsupported events simply to stop retries. Synthetic latency and retries are
not evidence of commercial delivery or a real provider SLA.

All restores in this offline composition stay quarantined outside SQLite, even if the
snapshot says active/consented or lost markers. There is no endpoint to release it.
Operational AUD01 still requires independent current evidence, inventory/reconciliation,
positive sync/channel/consent/window checks and authenticated audited release before
any worker is composed. Never erase unknown, generate replacement keys or replay old
sends when external idempotency expires. Ticket13 and production require new authorization.
