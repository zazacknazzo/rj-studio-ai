# Manual pending-Message recovery

> Baseline note: these commands describe the implemented synchronous runtime
> through Ticket 08. ADR 0006 keeps them as an operator fallback. Messaging
> Migration 05 will make durable executor polling the normal recovery path and
> will require a recovered AI Reply to own an Outbound Delivery.

This V1 operation is explicit and local. It has no scheduler, worker, queue, or
public administrative endpoint.

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
predecessor, or run this as a loop. Until Messaging Migration 05 is deployed,
no autonomous executor exists.

## Verify and delivery limit

Run the list command again and confirm the selected Message is absent after a
successful terminal recovery. The current WhatsApp provider replies only while
handling an inbound webhook; this CLI does not add proactive WhatsApp delivery
or print the AI Reply body. It safely restores the durable lifecycle and can
unblock later Messages, but a missed customer delivery requires the planned
Outbound Delivery capability or an operator's established manual process.
