# Fence automation with an explicit single-business channel binding

Status: accepted within the user's authorized offline Ticket 09 scope.

WABA identifies an account, not a Conversation or a phone number. Bind the
validated ingress configuration (WABA, business number, organization, profile)
immutably in one single-business row. Reuse the operational journal for account
observations and retain a separate applied-effect receipt. Both, the channel
state, generation suppression and cancellation of proven-unsubmitted work commit
in one short BEGIN IMMEDIATE transaction before ACK. Message scope validation is
not applied to account observations; event identities cannot cross those kinds.

There is no implicit active state. Missing binding or verification fails closed
for Telnyx only. A newly bound channel is verification_required. The database can
represent a previously verified active connection with explicit evidence, for
synthetic tests and future approved provisioning, but this ticket implements no
activation command. A non-active row cannot transition to active or be deleted
through ordinary SQL without changing the reviewed schema. Admin conversation
resume and Human Handoff release have no channel authority.

Every unseen valid lifecycle event applies in local journal insertion order.
That order is durable and deterministic for a database, not remote chronology;
we never sort textual event IDs or choose a winner by occurred_at. Offboard and
partner removal block; reconnect records verification_required. Every outcome
remains ineligible. Exact replay retains the first receipt and does not reapply;
contradictory canonical evidence rejects atomically. Future/old provider clocks
cannot open the gate. Ambiguous timestamps and unknown transitions reject without
ACK. Unknown raw values are not persisted or logged; future support and retry
handling require a separately approved policy (CX-29).

SQLite guards enforce the gate at admission, claim, reply and submission seams.
Blocking suppresses owned/pending generations without resetting attempts and
cancels pending/retryable/unmarked sending. Submitted/unknown/accepted evidence
survives; late proven-retryable outcomes retain their attempt and cancel locally.
The generation boundary rechecks the channel before LLM I/O and completion checks
again. There remains a check-to-LLM window (the result is fenced) and the existing
authorization-to-HTTP window: already authorized or started I/O cannot be recalled.
No transaction spans external calls. A future activation/rebinding implementation
must define a new verified epoch and prevent any old work from being revived.

Migration 0020 adds side tables and guards without rebuilding parent tables.
Unverified historical Telnyx work is suppressed/cancelled under the same rules;
Messages, attempts, status receipts and Meta/Twilio policy are preserved.
Downgrade requires explicit backup/restore. Channel/effect records share CX-01's
retention hold. No route, sender, account operation, readiness or pilot is enabled.
