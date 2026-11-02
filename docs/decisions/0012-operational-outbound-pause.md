# Cancel only proven-unsubmitted deliveries at operational pause

Status: accepted for explicitly authorized Ticket 04.

Extend ADR 0008's submission marker to the independent operational pause of
ADR 0011. SQLite control triggers finalize unsubmitted started attempts locally,
then cancel pending/retryable/unmarked sending in the same transaction as pause
and its effect receipt. A local `operational_pause_cancelled` attempt is failed
only in the existing attempt enum; it records cancellation, not provider failure.
No completed attempt or Message is rewritten. Migration 0016 applies these rules
to controls already paused before upgrade without replaying effects or revisions.

Acquisition and the existing one-shot authorization transaction require no active
operational pause. Authorization also retains owner, lease and policy handoff
checks and commits the marker before I/O. Cancelled claims lose their owners and
cannot resurrect. A database guard rejects bypassed authorization; a ready-state
trigger cancels a late proven-retryable result without overwriting its attempt.
Triggers keep control transitions and all retryable outcomes atomic even across
multiple processes, without a separate cancellation job or a lock spanning HTTP.

Unknown, accepted, sent, delivered and read remain evidence, not cancellation
candidates. Legacy rollback-mode rendering is fenced too. The policy-handoff
exception for unverified legacy unknown applies only outside operational pause;
release cannot turn that ambiguity into cancellation while paused. A handoff
confirmation remains permitted until operational pause, then follows the same
proven-unsubmitted rule as any other delivery. Handoff itself is unchanged.

An authorization committed before pause can still start HTTP afterwards. The
marker proves potential submission, never acceptance or delivery. Preserve late
results, monotonic callbacks and conservative unknown expiry; never resend to
compensate. This local transaction cannot promise external exactly-once or recall.
Authenticated commands remain Ticket 05. Journal/control retention on hold is
still a release blocker; this change neither purges data nor enables Telnyx.
