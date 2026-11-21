# Telnyx Coexistence Ticket 11 — offline text sender

Status: authorized by explicit user Ticket11 instruction, 2026-11-21, America/Sao_Paulo.
Baseline `07c1b7dc150d7eb1776b97d891cd29347adffd37`; branch11 only. User authorization
covers this spec's offline scope. Tickets12–13, activation, commercial credentials,
Telnyx API requests, public routes, runtime worker selection and production are excluded.

## Verified external contract

Consulted 2026-11-21: [endpoint](https://developers.telnyx.com/api-reference/whatsapp-messaging/send-a-whatsapp-message),
[OpenAPI](https://raw.githubusercontent.com/team-telnyx/openapi/master/openapi/spec3.json),
[idempotency](https://developers.telnyx.com/docs/development/api-fundamentals/idempotency),
[SDK](https://github.com/team-telnyx/telnyx-python/blob/master/README.md).
Public documentation fetches are separate from application transport; no API calls.
OpenAPI SHA256 `fc59cb60a25c5091e73889842c808f1db7b4c0bb36bbb0228ee9ed2f629eca18`;
idempotency Markdown SHA256 `ffb46a8a2039abc459544860a2ebf5d15917b8f4c1b83947291df26cca4c8e0d`.

POST https://api.telnyx.com/v2/messages/whatsapp, JSON `from`, `to`,
`type=WHATSAPP`, `messaging_profile_id`, `whatsapp_message={type:text,text:{body,preview_url:false}}`.
No SMS `/messages` or Meta Graph request. V1 deliberately permits only E.164 recipients,
although the current prefixed OpenAPI request schema also documents BSUID support.
Idempotency-Key is declared optional externally and mandatory locally. Scope is key,
organization, method and path; same query parameters/values and byte-identical body.
Only successful2xx responses replay for UP TO24h, not a minimum retention promise.
409/10036 means in progress;422/10027 means request conflict. Neither grants retry.
The SDK retries twice by default (connection/408/409/429/5xx), so no Telnyx SDK is used.
No provider timeout SLA is inferred; explicit local connect/read budgets are required.

The endpoint documents200 with `WhatsappResponse.data`: record_type/message,
direction/outbound, id (string, no UUID format constraint), type/WHATSAPP,
organization_id, messaging_profile_id, from.phone_number, array to[].phone_number/status,
and body. The schema lacks required lists for response identity; local acceptance is
intentionally stricter: require these identity fields and text body agreement, exactly
one recipient, recognized nonfailure status and no conflicting evidence. Missing identity,
unknown status, malformed JSON, duplicate keys or body mismatch means unknown, not guessed
acceptance. HTTP status does not supply sent/delivered/read evidence; T08 ledger owns it.
Examples default to audio and are not the free-form request contract. Unknown additional
fields are ignored, never logged. Do not interpret message.echo as AI acceptance.

## Request and durable identity

Build immutable exact request before writer authorization. Fixed POST/HTTPS/host/path,
empty canonical query, JSON UTF8 with sorted keys, compact separators, no Unicode
normalization, explicit preview_url=false. Header Idempotency-Key uses T10 UUIDv4;
Content-Type is application/json. No credential accepted or stored by this offline sender.
Bind organization/profile/channel/recipient/modality/method/scheme/host/path/query/header
identity and exact body bytes using versioned HMAC-SHA256 with an injected32-byte or longer
integrity key and key identifier. This is a local integrity key, not a Telnyx credential.
It must remain stable outside SQLite across restarts; losing/rotating it fails closed
for previously bound deliveries. Store only key ID/MAC beside durable submission key,
not body or an unkeyed content hash. This reduces predictable-content guessing by a
DB-only observer; it is not anonymization or a fence against old restores.

Additive migration0022 stores immutable bindings, retains them through terminal purge,
and rejects REPLACE/reuse. Numeric delivery IDs must not be the retained identity.
Under the existing BEGIN IMMEDIATE seam, revalidate request canonical bytes and actual
lifecycle organization/profile/channel, compare/insert binding and set all markers together.
All existing T10 owner/lease/window/consent/revision/pause/handoff/order/conflict/channel
checks remain. No SQLite transaction spans transport. Existing fake sender contract
remains available for historic offline tests; concrete Telnyx sender requires prepared
request integration and has no generic send fallback.

## Transport and result policy

Only an explicitly injected exchange callable; no network client/default, SDK, credentials,
redirect handler, runtime factory or retries. One invocation per committed authorization.
Pass explicit connect/read budgets, retries=0 and follow_redirects=false. Revalidate
prepared request before invocation. Pre-transport preparation failure is proven local:
retain an unmarked attempt with NOT_SUBMITTED evidence through existing retry policy.
After marker, any exception or malformed/error response conservatively unknown, even
connection timeout: no adapter proof of non-submission. No key replacement or resend.
422/10027 retains fixed key-conflict reason;409/10036 retains in-progress reason;
other409/422,429/5xx/redirects,2xx incomplete/mismatch and lost responses all unknown.
No remote status alone proves a permanent safe rejection or retry eligibility.

Flow: durable claim → owner/lease → prepare/verify → atomic gates/binding/markers commit →
intercepted transport → strict response → existing durable finalize/status reconciliation.
Callback before/after response remains scoped T08 evidence; failure finalizing acceptance
must not trigger another exchange. Crash after marker expires to unknown. Authorization
before pause/disconnect can still invoke transport afterwards (CX06, no recall).

## Restore recovery contract — AUD01 OPEN

Old snapshots can erase later claim/marker/acceptance/disconnect/consent/clock data.
Integrity/migrations/extra fields inside the restored DB do not prove freshness.
Every operational restore MUST enter quarantine with all outbound work disabled by a
control outside the restored snapshot, before any worker/transport is composed.
Future authorized T12–13 composition must inventory all potentially submitted work,
reconcile external message/status and account synchronization, revalidate channel binding,
current consent/window and identity against independent current evidence, and require
an authenticated audited release using an external epoch/fence or equivalent verified
procedure. If evidence is unavailable, remain quarantined/unknown. Never generate new
keys or make unknown retryable, including after external retention expires.

T11 only documents contract and tests SQLite snapshots before claim, before marker,
before disconnect and after acceptance; tests that reproduce unsafe reauthorization
must be explicitly labelled known failure/gate, not mitigation. No operational quarantine,
activation or recovery implementation is authorized. AUD01 therefore blocks real sending.

## Verification and checkpoints

Private0700 temporary parent, explicit --basetemp, sanitized environment, Python IP guard
including children. Update dev pytest constraint to a fixed-advisory-capable9.x range and
upgrade pip only in isolated venv; runtime dependencies unchanged. Resolve from explicit
trusted PyPI index; record versions/full suite/pip-audit, including failures/skips.
CP0 spec/ADR/handoff → CP1 exact request/binding → CP2 injected responses → CP3 integration →
CP4 adversarial restore/restart/SQLite → CP5 full checks and independent Standards/Spec/
adversarial reviews → CP6 report and issue11 evidence. Normal commits/push + verify remote
after each, no main merge/force push. Independent reviewers inspect code and execute their
own tests. Record executed/inspected/simulated/unproven/not executed distinctly.

Required coverage: exact bytes/key/material mutation, organization/host/path/query,
response2xx valid/incomplete/malformed/scope/status,409/422 codes,429/5xx, connect/read
failures/disconnect/lost response, pretransport failure, marker/crash, single auth and
workers, owner/lease, pause before/after, handoff/lifecycle/reconnect, consent/window,
BSUID/conflict, early/late callbacks, commit rollback, migration/history/purge/reused IDs,
old snapshots and external idempotency expiry, no network/log secrets, legacy regressions.
Checks: pytest integral, Ruff check/format, compileall, pip check, diff check, Gitleaks,
pip-audit. AUD01 unresolved, AUD02 resolved only if actual corrected versions checked,
AUD03 requires reproducible resumption rehearsal; human-exclusive branch writing remains.
Final report A–O and issue11 evidence close no checkboxes. Separate offline eligibility
from operational NO-GO, then stop and request direct orchestrator audit.
