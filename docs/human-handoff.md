# Human Handoff operations

The initial responsible operator is the product owner. No external notification
or routing service is implemented. The owner must inspect handoffs explicitly:

```bash
.venv/bin/rj-studio-maintenance list-handoffs
.venv/bin/rj-studio-maintenance release-handoff \
  --conversation-id <id> --owner-token <current-episode-token>
```

For a specific database, put `--database-path <path>` before the subcommand.
Listing shows internal Conversation/episode IDs, a safe reason code, and an
activation timestamp. It prints no Customer address, Message body, or model
reason text. The token is a local concurrency fence, not a provider credential.
Release returns exit code 0 only for the current active episode; a stale,
wrong, or already-released token returns 1 without changing state.

Release resumes eligibility for **future inbound Messages only**. Messages
received while active remain `suppressed` on retry/restart and have no AI Reply.
An unsent confirmation is cancelled on release; accepted/sent work cannot be
recalled. Possible in-flight/unknown outcomes remain unresolved and can still
block Conversation ordering. Use `list-blocked-deliveries` to inspect metadata;
do not retry unknown work simply because the handoff was released.

Recognized technical risk, relevant complaint, explicit human request, trusted
knowledge rules, a validated model proposal, or exhausted safe generation can
activate handoff. A recognized physical symptom receives conditional safety
guidance without diagnosis. Trusted rendering from Ticket 09 remains the factual
boundary. Synthetic deterministic cases live in `tests/test_human_handoff.py`;
real-model handoff quality still belongs to the V1 eval gate.

Back up the database before applying migration 0009. There is no automatic
downgrade that discards suspension state. The 90-day Message purge retains an
active handoff even when all its Messages expire. Explicit Conversation deletion
also deletes that Conversation's handoff and must not be used as release.

Design and residual submission race: [ADR 0008](decisions/0008-durable-human-handoff.md).

Ticket 11's [appointment-interest episode](appointment-interest.md) retains only
the minimum declared preferences for the assuming person. Its explicit
`inspect-appointment-interest` command is separate from metadata-only listing.
Release ends the linked intake; it does not reuse those preferences or revive
old Messages.
