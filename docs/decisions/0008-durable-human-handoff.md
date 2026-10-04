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

## Trusted authorization amendment — 2026-10-04

The product owner approved a general gate after a completed model proposal
reopened handoff on a benign greeting following valid manual release. Model
`handoff` and its textual reason are advisory: normalization into a safe code
is privacy protection, never authorization. `handoff.apply_handoff_policy`
clears only those two fields when no existing policy branch requires handoff;
`grounding.finalize_reply` then validates/renders the same remaining plan. A
trusted branch authorizes its own reason irrespective of the model boolean.
Generation failures and deterministic appointment/cancellation completion
retain their existing application policies and atomic persistence. No migration
or history/release/context changes are needed.

We reject treating every probabilistic proposal as terminal Conversation state,
accepting that a model-only explanation cannot establish a new safety policy.
Existing current-Message risk/human/complaint/legal/payment triggers, approved
Knowledge conditions, invalid factual states and appointment rules take priority.
`MODEL_REQUEST` remains readable for historical episodes, not a new authority.

Separate limitation, intentionally outside this patch: recognized `HUMAN_REQUEST`,
`COMPLAINT`, and applicable `APPOINTMENT_CHANGE` Intents still activate existing
policy even when only proposed by the model. False classifications can therefore
still cause needless handoff. Current deterministic safety recognition is also
bounded: e.g. face swelling without a recognized risk phrase, a named-owner
request without HUMAN_REQUEST, or dissatisfaction without COMPLAINT may lack
policy evidence. A free-form model reason no longer fills that gap. Those
recognition/Intent trust limits need a separately approved policy change; do not
weaken factual validation or restore blanket model authorization to hide them.
