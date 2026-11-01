"""Private journal writes inside the caller's ingress transaction; no operational effects."""

import sqlite3
from datetime import UTC

from rj_studio_ai.domain import (
    ChannelAvailabilityChanged,
    ChannelScope,
    HumanMessageObserved,
    MessageEdited,
    MessageRevoked,
    classify_provider_event,
)

OperationalEvent = (
    HumanMessageObserved | MessageEdited | MessageRevoked | ChannelAvailabilityChanged
)
OPERATIONAL_EVENT_TYPES = (
    HumanMessageObserved,
    MessageEdited,
    MessageRevoked,
    ChannelAvailabilityChanged,
)

# Explicit columns keep payloads and Message bodies outside the journal.
_COLUMNS = (
    "provider",
    "scope_kind",
    "scope_id",
    "event_id",
    "kind",
    "origin",
    "occurred_at",
    "provider_message_id",
    "customer_address",
    "message_occurred_at",
    "original_namespace",
    "original_message_id",
    "availability",
    "reason",
)


def record_operational_event(
    connection: sqlite3.Connection,
    event: OperationalEvent,
    *,
    received_at: str,
) -> None:
    """Dedupe only event identity; references do not imply a Message association."""
    kind = classify_provider_event(event)
    metadata = event.metadata
    lifecycle = isinstance(event, ChannelAvailabilityChanged)
    original = (
        event.original_message if isinstance(event, (MessageEdited, MessageRevoked)) else None
    )
    values = (
        event.provider,
        event.scope.value if lifecycle else ChannelScope.CHANNEL.value,
        event.scope_id if lifecycle else event.channel_id,
        metadata.event_id,
        kind.value,
        metadata.origin.value,
        metadata.occurred_at.astimezone(UTC).isoformat(),
        None if lifecycle else event.provider_message_id,
        None if lifecycle else event.customer_address,
        metadata.message_occurred_at.astimezone(UTC).isoformat()
        if metadata.message_occurred_at is not None
        else None,
        original.namespace if original is not None else None,
        original.message_id if original is not None else None,
        event.availability.value if lifecycle else None,
        event.reason.value if lifecycle else None,
    )
    aliases = sorted({(alias.namespace, alias.message_id) for alias in metadata.message_aliases})
    row = connection.execute(
        f"SELECT id, {', '.join(_COLUMNS)} FROM operational_events "
        "WHERE provider = ? AND scope_kind = ? AND scope_id = ? AND event_id = ?",
        values[:4],
    ).fetchone()
    if row is not None:
        stored_aliases = connection.execute(
            "SELECT namespace, message_id FROM operational_event_aliases "
            "WHERE event_record_id = ? ORDER BY namespace, message_id",
            (row[0],),
        ).fetchall()
        if tuple(row[1:]) != values or stored_aliases != aliases:
            raise ValueError("Conflicting canonical operational event identity")
        return
    cursor = connection.execute(
        f"INSERT INTO operational_events ({', '.join(_COLUMNS)}, received_at) "
        f"VALUES ({', '.join('?' for _ in range(len(_COLUMNS) + 1))})",
        (*values, received_at),
    )
    connection.executemany(
        "INSERT INTO operational_event_aliases (event_record_id, namespace, message_id) "
        "VALUES (?, ?, ?)",
        [(cursor.lastrowid, namespace, message_id) for namespace, message_id in aliases],
    )
