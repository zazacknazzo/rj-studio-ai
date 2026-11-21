# Telnyx Coexistence Ticket 12 — offline ASGI composition

Status: authorized by explicit Ticket12 request and issue11 approval
https://github.com/zazacknazzo/rj-studio-ai/issues/11#issuecomment-7062936123.
User confirmed exclusive Git ownership in this chat on 2026-11-21.
Baseline: `246fe79a9bed4b202c49d3b2780320f6d5a0ca9c`.
Only branch `codex/telnyx-coexistence-12-composition` may be published.
This spec records the already authorized offline scope before implementation.

## Composition and boundaries

Provide an explicitly offline ASGI factory, never imported/mounted by production
main/provider factories/configuration. No commercial key, HTTP client, LLM, sender,
executor, startup polling or activation. Use real SQLite and ASGI/TestClient with
synthetic signed envelopes; keep Meta/Twilio and intelligence behavior unchanged.
Preserve the raw ASGI header sequence; reject duplicate signature/timestamp before
conversion to a dictionary, also reject ambiguous content-type/content-length and
transfer-encoding with content-length. Keep original body bytes, enforce stream size
regardless of missing/lying length, reject malformed/mismatched lengths, and bound
read duration. Signature verification must precede JSON; scope precedes effects.
One documented Telnyx envelope per HTTP request; arrays are not an invented wire batch.
Local tuple composition remains atomic, including supported/unsupported siblings.

## Durability and deadline — CX24/CX30

Internal total budget 1.5 seconds, work budget 1.35 seconds, 0.15 seconds reserved
for final ACK checks/HTTP overhead; body read cap 0.5 seconds within the same budget.
Time includes queueing, auth/parsing, SQLite lock/SQL/commit and response preparation.
Use monotonic deadlines, cap SQLite busy waiting by remaining work, precommit and
postcommit checks; 204 only after commit and while ACK budget remains. Lock/SQL/
commit/deadline errors are non2xx; a late durable commit is replayed idempotently.
Filesystem fsync and ASGI server/socket backpressure cannot be hard-preempted by this
application: measured offline p95/p99 are evidence, not a production 2-second SLA.
No detached background persistence or ACK-before-commit.

## Unsupported event policy — CX29

Retain existing conservative scope/parser contracts. Media or future body types,
unknown events/transitions/statuses, malformed authenticated envelopes and redundant
WABA routes do not become successful empty batches. Return 422; invalid signatures
403, malformed HTTP400/413/415, read timeout408, persistence/deadline503.
A finite aggregate rejection counter is durable before returning422: fixed reason,
count and first/last local receipt only, no raw payload, hashes, event/customer/channel
IDs or external error strings. It is visibility, not a durable Message receipt or a
recovery archive. Duplicate retries increment observations; never claim deduped event
counts. No supported siblings commit from an invalid local tuple/wire array.

Counter failure returns503 and remains visible in bounded process metrics. Known
supported events retain existing journal/receipts/effects atomically before204.
Echo of media still applies human pause without content. Unknown lifecycle never
activates. Alerts/operator handling, richer support, subscriptions and provider retry/
failover validation remain pre-pilot gates. Never ACK unsupported to suppress retries.
New counters have bounded row cardinality and no new personal data; operational
retention/deletion and backup policy remain CX01, no erasure promise.

## Restore quarantine and exact egress — AUD01/CX35

Each offline composition starts in a quarantine outside the restored SQLite file:
no outbound/generation workers can be constructed or started by this composition,
no authenticated release endpoint or release capability exists in Ticket12.
Do not infer permission from restored active/consent/HMAC/markers. Simulate snapshots
before claim, marker, disconnect, old snapshot after acceptance and external key expiry,
and restart: composition remains quarantined, zero intercepted outgoing calls.
A strict store option used by the offline composition refuses Telnyx authorization
without the exact prepared HTTP request inside the existing writer transaction.
Existing HMAC binding/owner/lease/channel/pause/handoff/window/consent gates remain.
Meta/Twilio and historical internal callers retain default compatibility.

This is a tested closed composition, not a complete operational antirollback system.
AUD01 stays OPEN: real deployment requires an independently durable current epoch or
verified equivalent outside backups, inventory/reconciliation of potentially submitted
work, current channel/consent/window evidence, authenticated audited release and
freshness/rollback tests against real infrastructure. No release is implemented;
unknown remains unknown, keys are not replaced, expired external idempotency does not
permit old sends. Ticket13 and all operational egress remain unauthorized.

## Readiness, evidence and checkpoints

Expose distinct ingress, persistence, administration, generation, egress and operational
channel readiness; local health proves only process responsiveness. Ingress may work
while lifecycle is blocked; generation/egress/operational remain false in quarantine.
Metrics have finite status/reason/bucket labels, no text/headers/secrets/IDs; avoid
unbounded latency/event lists. Persistence readiness includes schema/pragmas and bounded
writability probe. No claim of credential, sync, external account or commercial readiness.

CP0 spec/ADR/handoff; CP1 raw headers/streaming; CP2 auth/parser/ingress; CP3 durability/
ACK/deadline; CP4 unsupported/readiness; CP5 restore/egress/concurrency; CP6 independent
Standards, Spec, Security/Reliability reviews and corrections/full checks; CP7 A–O/issue11.
After each: relevant checks, handoff, coherent normal commit/push, remote SHA verification.
Tests: raw duplicate headers, signatures/auth-first, fragment/oversize/missing/lying length,
invalid JSON/media/future/batches, commit/rollback/lock, lost ACK/replay/concurrency/deadline,
callbacks/lifecycle/consent/status contradictions, restore and exact egress negative tests,
full Tickets01–11/Meta/Twilio regressions. Full pytest under Python IP network guard,
Ruff check/format, compileall, pip check/audit, Gitleaks, diff check and independent reviews.
Reviewers may run own probes and write separate reports; only primary writer commits/pushes.
No P1/P2 closure without evidence; no synthetic test is a real Telnyx validation.

## Official contracts inspected 2026-11-21

- https://developers.telnyx.com/docs/messaging/messages/receiving-webhooks.md
  requires2s ACK, Ed25519 timestamp|raw-body, bounded retries/failover, no order guarantee.
- https://developers.telnyx.com/docs/messaging/whatsapp/coexistence/webhooks.md
  echo best-effort; WABA messages creates duplicate path; lifecycle does not prove sync.
- https://developers.telnyx.com/docs/development/api-fundamentals/idempotency.md
  up to24h, scope organization/method/path/key, identical body, no unknown-retry authority.

Documentation examples recommending immediate ACK or retaining whole payload do not
override this project's commit-before-ACK and minimization requirements.
At completion STOP and request direct orchestrator audit. OFFLINE candidate only;
PRODUCTION NO-GO. No risk checkboxes closed, no exceptions accepted, no merge/main,
Baileys, intelligence changes, commercial credentials, real Telnyx calls or activation.

## CP5 reviewed refinements

SQLite writer wait cap is0.5s, always reduced to remaining workbudget;0.05s produced
observable503 contention at eight-way load. Load evidence reports first-attempt
204/503 mix and p95/p99, then retries identical503 envelopes after draining and proves
one durable admission per logical Message. Backpressure is not hidden as success.
Admission queue acquisition is deadline-bounded before dispatch. Admitted thread work
is shielded/drained even under repeated raw asyncio cancellation; capacity remains
reserved until completion, cancellation propagates without ACK. Metrics run after
ASGI response sending, avoiding a lock after the final ACK deadline check.
Constructor rejects an unquarantined store, not only the public factory.
Strict intercepted-store tests inject a stable independent TelnyxRequestSigner:
missing/tampered requests fail HMAC verification in the writer before authorization.
The actual ASGI store remains completely quarantined (even valid requests deny).
Default historical store behavior is compatibility, not an operational entry point.
