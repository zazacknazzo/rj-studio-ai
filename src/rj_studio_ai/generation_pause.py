"""Apply exact human-activity evidence in the caller's short SQLite transaction."""

import sqlite3


def apply_pending_human_pauses(
    connection: sqlite3.Connection,
    *,
    timestamp: str,
    provider: str | None = None,
    customer_address: str | None = None,
) -> None:
    """An event receipt is not an effect receipt; aliases never resolve identity."""
    events = connection.execute(
        """
        SELECT event.id, event.provider, event.scope_id, event.customer_address,
               event.provider_message_id
        FROM operational_events AS event
        WHERE event.kind = 'human_activity'
          AND (? IS NULL OR event.provider = ?)
          AND (? IS NULL OR event.customer_address = ?)
          AND NOT EXISTS (
              SELECT 1 FROM human_pause_effects AS effect
              WHERE effect.provider = event.provider AND effect.channel_id = event.scope_id
                AND effect.customer_address = event.customer_address
                AND effect.provider_message_id = event.provider_message_id
          )
        ORDER BY event.id
        """,
        (provider, provider, customer_address, customer_address),
    ).fetchall()
    for event_id, event_provider, channel, customer, message_id in events:
        # Recheck within the loop: several envelopes may describe one logical Message.
        if connection.execute(
            "SELECT 1 FROM human_pause_effects WHERE provider = ? AND channel_id = ? "
            "AND customer_address = ? AND provider_message_id = ?",
            (event_provider, channel, customer, message_id),
        ).fetchone():
            continue
        conversation = connection.execute(
            "SELECT id FROM conversations WHERE provider = ? AND customer_address = ?",
            (event_provider, customer),
        ).fetchone()
        if conversation is None:
            conversation_id = connection.execute(
                "INSERT INTO conversations (provider, customer_address, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) RETURNING id",
                (event_provider, customer, timestamp, timestamp),
            ).fetchone()[0]
        else:
            conversation_id = conversation[0]
            channels = connection.execute(
                "SELECT recipient_address FROM messages "
                "WHERE conversation_id = ? AND direction = 'inbound' "
                "UNION SELECT delivery.provider_channel_id FROM outbound_deliveries AS delivery "
                "JOIN messages ON messages.id = delivery.outbound_message_id "
                "WHERE messages.conversation_id = ? "
                "UNION SELECT channel_id FROM conversation_automation_controls "
                "WHERE conversation_id = ?",
                (conversation_id, conversation_id, conversation_id),
            ).fetchall()
            if channels != [(channel,)]:
                # No evidence or conflicting channels: keep the receipt unresolved.
                continue
        revision = connection.execute(
            """
            INSERT INTO conversation_automation_controls
                (conversation_id, channel_id, paused, revision, updated_at)
            VALUES (?, ?, 1, 1, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET paused = 1,
                revision = revision + 1, updated_at = excluded.updated_at
            RETURNING revision
            """,
            (conversation_id, channel, timestamp),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO human_pause_effects (event_record_id, conversation_id, provider,
                channel_id, customer_address, provider_message_id, applied_at, revision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                conversation_id,
                event_provider,
                channel,
                customer,
                message_id,
                timestamp,
                revision,
            ),
        )
