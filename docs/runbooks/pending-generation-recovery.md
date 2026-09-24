# Manual pending-Message recovery

> Messaging Migration 05 uses durable executor polling for normal recovery.
> These commands remain an operator fallback for selected Messages.

This V1 operation is explicit and local. It has no public administrative endpoint.

## List work

```bash
rj-studio-maintenance --database-path data/rj_studio_ai.db list-pending-generations
```

The command prints only inbound Message ID, Conversation ID, lifecycle state,
attempt count, timestamps, lease status, and whether an earlier Message blocks
it. It never prints Customer addresses or Message bodies.

`retryable` means no owner currently holds the Message. `processing` with
`stale=yes` means its lease has expired. A valid active lease is not listed as
stale. `blocked_by_predecessor=yes` means recover the earlier non-terminal
Message first.

## Recover one selected Message

```bash
rj-studio-maintenance --database-path data/rj_studio_ai.db recover-generation \
  --inbound-message-id 123
```

The command reuses the normal durable claim, ordering, deadline, generation,
metrics, and completion flow. It rejects active claims, `completed`,
`suppressed`, unknown, and predecessor-blocked Messages. A nonzero exit code
means no terminal AI Reply was persisted; inspect the listed state before a
later explicit attempt.

Do not edit lifecycle rows directly, recover a later Message ahead of its
predecessor, or run this as a loop. In proactive mode, normal retryable and
expired work is already recovered by the Processing Executor. Run this command
with the same `DELIVERY_MODE` and Salon Knowledge configuration as the app.

## Verify and delivery limit

Run the list command again and confirm the selected Message is absent after a
successful terminal recovery. In proactive mode the recovered AI Reply receives
a `pending` Outbound Delivery in the same transaction; the Outbound Executor
finds it through SQLite polling. In legacy mode the CLI creates an unverified
delivery requiring the established reconciliation process. The command never
prints the AI Reply body.
