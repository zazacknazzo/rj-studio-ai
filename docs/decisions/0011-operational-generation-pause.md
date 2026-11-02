# Fence generation with an independent operational pause revision

Status: accepted for the explicitly authorized Ticket 03 scope.

Human activity uses the Ticket 02 journal, then a separate applied-effect receipt
keyed by exact provider/channel/Customer/logical Message identity. Existing event
receipts are not evidence of applied pause. Startup reconciles unapplied human
observations before executors start. Aliases cannot select a Conversation.
Existing Conversations require an unambiguous matching channel from retained
Messages/deliveries or an existing control; otherwise the event stays unresolved.
A first canonical human observation can establish a paused identity without any
Message. Controlled Conversations reject inbound channel changes; the V1 model
still does not support multiple channels for one provider/Customer identity.

The side-table pause invalidates every retryable/processing owner, including
expired or exhausted attempts, and preserves attempt counts. SQLite's old CHECK
allowed suppressed only at attempt zero. Rebuild only the leaf processing table
transactionally, preserving FKs, rows, indexes and trigger definitions. The new
revision column captures control revision at claim time. Finalization checks that
revision, active pause, owner and lease before inserting reply/outbox/intake in the
same short transaction. Terminal suppression remains immutable; no timeout or
policy-handoff release resumes it. No external call holds a SQLite transaction.

The commit boundary resolves concurrency. Completion before pause keeps its
persisted reply; pause before completion prevents a new reply. This does not stop
an already started LLM request, cancel an outbox item, or recall an external send.
Ticket 04 must fence outbound, including existing handoff confirmations. Ticket 05
must add authenticated operations. Operational pause does not alter Human Handoff.

Pause/effect evidence cannot be deleted by raw-message retention or Conversation
maintenance; explicit deletion fails for a retained control/effect. Journal and
controls remain on hold. Unbounded retention is a release blocker, not a privacy
or production readiness guarantee. No integration Telnyx is enabled by this ADR.
