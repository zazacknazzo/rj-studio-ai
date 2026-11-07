# Ticket 05 — authenticated Conversation automation operations

Status: approved by explicit user request; base 1901a364123c38dc0e1d36a8ea9706b035eef420.
Only Ticket 05 is authorized, including normal push after independent review and audit.

Test seams: FastAPI administrative requests against temporary real SQLite, generation
and delivery runners, migration and concurrent transactions. These are the observable
boundaries explicitly required by the user's test matrix. No live providers.

GET /admin/conversations/{opaque_id}/automation is read-only. POST at the same path
with /pause or /resume accepts only operation_id (32 lowercase hexadecimal characters, UUID.hex) and expected_revision (int>=0).
Responses contain opaque Conversation identity, paused, revision, handoff_active,
in_flight_possible, unresolved_delivery. No Message, phone, external ID or episode token.
Errors use generic codes: 401 authentication, 403 permission/resource, 404 absent,
409 revision/idempotency/channel conflict, 422 invalid input, 503 unavailable.
No automatic handoff release. This narrows the original optional release proposal
according to the current user requirement to preserve handoff independently.

A single configured operator uses Authorization: Bearer with a random secret of at
least 32 characters. Only its SHA256 digest is configured, excluded from repr/dumps.
Explicit permissions (read/control) and opaque Conversation allowlist or explicit '*'
authorize access. Missing/malformed configuration fails closed; no query credentials.
TLS and header redaction at the deployment proxy are required. No user registration.

One side table maps existing/new Conversations to random opaque IDs; it contains no
second automation state. Operations use the existing controls with CAS and increment
revision. Operation receipts preserve original response for exact replay, conflict on
key reuse with different intent, and record minimal operator/action/revision audit.
All effects/receipt commit together. Resume never revives suppressed/cancelled work,
resolves unknown/failed or changes handoff. No read creates state.

Echo policy reuses human_pause_effects: already applied logical Message stays deduped
across resume; unapplied human activity conservatively repauses irrespective of remote
timestamp or event ID order. Unresolved identity remains unresolved; no alias guessing.
Resume cannot guarantee absence of unobserved manual activity. New inbounds with validated origin time strictly after the persisted resume cutoff
and no future/contradictory clock evidence are eligible under existing ordering/handoff rules, not guaranteed delivery.

Retained journal/controls/operation receipts have no automatic purge and remain a
release blocker. Echo best-effort and marker-to-HTTP race persist. Tickets06–13,
real onboarding, paid calls, WhatsApp and frozen intelligence changes are excluded.


Resume cutoff is stored in the existing control. Missing/old/future/contradictory
source times suppress the admission permanently, even if received after resume.
Legacy constructors/adapters remain compatible in unresumed Conversations; legacy
messages without source metadata after resume are conservatively suppressed until
an adapter supplies trustworthy message_occurred_at. No receipt time substitutes it.
Late proven-retryable delivery from an older operational revision is cancelled even
after resume, using its existing generation revision; acceptance/unknown remain valid.

The cutoff is monotonic across local clock regressions and interleaved echoes.
Clock regressions may prolong suppression; they cannot lower an already retained
boundary. Plausible but incorrect remote timestamps remain a documented limitation.
Tests inject the local clock for admission boundaries, force both writer orders for
pause/resume and echo/resume, and abruptly terminate a child process before and after
resume commit to verify rollback and operation receipt replay.
