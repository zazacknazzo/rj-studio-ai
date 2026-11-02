# Authenticated operations and future-only resume

Status: accepted for authorized Ticket 05.

Keep one automation authority in conversation_automation_controls. The private API
uses a dedicated random Bearer secret verified against a configured SHA256 digest,
constant-time comparison, explicit read/control permissions and explicit resource
allowlist (or '*' for the single business). Operator identity is an opaque audit
label. Owner tokens, episode tokens, revision and provider secrets grant no access.
Absent/invalid configuration disables these routes, not ordinary messaging.

A side table assigns random 128-bit opaque Conversation identifiers on migration
and insertion. Queries never create state. Mutation compares expected revision and
stores an immutable operation receipt in the same BEGIN IMMEDIATE transaction as
control changes. Exact operation replay returns the original result even if state
has since changed; callers must GET for current state. Conflicting reuse is rejected.
CAS applies to both pause and resume. Resume never releases policy handoff.

Resume persists a cutoff. Only authenticated canonical source Message times strictly
later than cutoff, no later than envelope time, and no later than local receipt are
eligible. Old, missing or contradictory evidence is terminal suppressed. Existing
Meta/Twilio payloads without source provenance remain compatible before any resume,
but are conservatively suppressed afterwards. Supporting trustworthy source time in
those adapters requires separate adapter work; receipt time cannot stand in for it.

Retain generation revision as the delivery's existing authorization lineage: a
late proven-retryable result whose generation predates pause/resume is cancelled,
even when pause is currently clear. Accepted/unknown evidence is never discarded.
Known human effect receipts remain deduped across resume. An unseen logical human
Message repauses, even with ancient timestamps or aliases matching an old Message.
No reliable total external event order is claimed. Delayed evidence can require
another operator decision; absence of echo is not absence of human activity.

Operation receipts have the same explicit retention hold as operational evidence;
no startup deletion. Unbounded retention remains a release blocker. Marker-to-HTTP
race, best-effort echoes, real-provider eligibility and unauthorized pilot remain
limits. This API adds no frontend, CRM, SaaS, provider connection or intelligence.
