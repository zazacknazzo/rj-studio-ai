# Durable Conversation handoff and submission fencing

Status: accepted

Human Handoff is a Conversation episode, not model text. A short SQLite
transaction validates generation ownership, creates one trusted confirmation
and its Outbound Delivery, completes processing, records the active episode
and safe reason, cancels proven-unsent work, and suppresses waiting Messages.
An inbound insert trigger suppresses new Messages while the episode is active.
Manual release compares the episode token and changes future admission only.

Migration 0009 uses a one-to-one side table instead of rebuilding
`conversations`: dropping that parent table with foreign keys enabled could
cascade-delete existing Messages. Existing data is preserved and no historical
handoff is inferred. Downgrade requires an explicit backup/restore plan rather
than silently dropping durable suspension state.

Each confirmation delivery carries its episode token. Only that confirmation
may submit while handoff is active. A durable `submission_started_at` marker is
committed after owner/lease/policy validation immediately before external HTTP,
outside the transaction. Pending/retryable and claimed-but-unmarked work can
be cancelled; possibly submitted work cannot. Existing sending/unknown rows
are conservatively marked on upgrade. A proven-not-accepted result arriving
after release is cancelled instead of scheduling an orphaned confirmation.

The marker cannot atomically coincide with a remote HTTP request. Handoff or
release can occur after authorization, including in the gap before HTTP starts;
that already-authorized attempt may escape. Acceptance is preserved, ambiguity
remains unknown, and neither is retried or pretended cancelled. Avoiding this
race would require holding a local lock across external I/O and still could not
recall a submitted request. This residual is explicitly accepted by the spec.

Release does not resolve unknown/failed outcomes or bypass Conversation
ordering. Message purge preserves an active episode; explicit Conversation
deletion remains a separate destructive maintenance operation. Local inspection
and release expose only operational identifiers, safe reasons, and timestamps.
