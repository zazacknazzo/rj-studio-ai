"""Minimal inbound provenance in the existing ingress transaction, with no content copy."""

import json
import sqlite3
from datetime import UTC

from rj_studio_ai.domain import InboundMessageReceived


def record_inbound_event(
    connection: sqlite3.Connection, event: InboundMessageReceived, *, received_at: str
) -> bool:
    """Return whether this logical Message is new; receipts survive content purge."""
    metadata = event.metadata
    if metadata is None:
        raise ValueError("Inbound receipt requires provenance")
    source = (
        metadata.message_occurred_at.astimezone(UTC).isoformat()
        if metadata.message_occurred_at is not None
        else None
    )
    values = (
        event.provider,
        event.recipient_address,
        event.customer_address,
        metadata.event_id,
        event.provider_message_id,
        metadata.occurred_at.astimezone(UTC).isoformat(),
        source,
        json.dumps(sorted({(a.namespace, a.message_id) for a in metadata.message_aliases})),
    )
    row = connection.execute(
        "SELECT provider,channel_id,customer_address,event_id,provider_message_id,"
        "occurred_at,message_occurred_at,aliases_json FROM inbound_event_receipts "
        "WHERE provider=? AND channel_id=? AND event_id=?",
        (event.provider, event.recipient_address, metadata.event_id),
    ).fetchone()
    if row is not None and row != values:
        raise ValueError("Conflicting inbound event identity")
    prior = connection.execute(
        "SELECT channel_id,customer_address,message_occurred_at FROM inbound_event_receipts "
        "WHERE provider=? AND provider_message_id=? LIMIT 1",
        (event.provider, event.provider_message_id),
    ).fetchone()
    if prior is not None and prior != (event.recipient_address, event.customer_address, source):
        raise ValueError("Conflicting inbound Message identity")
    stored = connection.execute(
        "SELECT messages.body,messages.recipient_address,conversations.customer_address "
        "FROM messages JOIN conversations ON conversations.id=messages.conversation_id "
        "WHERE messages.provider=? AND provider_message_id=? AND direction='inbound'",
        (event.provider, event.provider_message_id),
    ).fetchone()
    if stored is not None and stored != (
        event.body,
        event.recipient_address,
        event.customer_address,
    ):
        raise ValueError("Conflicting inbound Message identity")
    if row is None:
        connection.execute(
            "INSERT INTO inbound_event_receipts(provider,channel_id,customer_address,event_id,"
            "provider_message_id,occurred_at,message_occurred_at,aliases_json,received_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (*values, received_at),
        )
    return prior is None


def validate_message_scope(connection: sqlite3.Connection, event: object) -> None:
    """Validate the single-channel ingress identity before any effect or admission.

    Ingress explicitly requests this stricter provenance seam. Existing adapters keep
    their approved behavior. Aliases are evidence, never lookup keys.
    """
    from rj_studio_ai.domain import (
        HumanMessageObserved,
        MessageEdited,
        MessageRevoked,
        classify_provider_event,
    )

    if type(event) not in (
        InboundMessageReceived,
        HumanMessageObserved,
        MessageEdited,
        MessageRevoked,
    ):
        raise ValueError("Unsupported Message observation")
    if event.metadata is None:
        raise ValueError("Message observation requires provenance")
    kind = classify_provider_event(event).value
    channel = (
        event.recipient_address if isinstance(event, InboundMessageReceived) else event.channel_id
    )
    original = (
        event.original_message if isinstance(event, (MessageEdited, MessageRevoked)) else None
    )
    identity = (
        kind,
        channel,
        event.customer_address,
        original.namespace if original else None,
        original.message_id if original else None,
    )
    observations = connection.execute(
        "SELECT kind,scope_id,customer_address,original_namespace,original_message_id "
        "FROM operational_events WHERE provider=? AND provider_message_id=? "
        "UNION ALL SELECT 'customer_message',channel_id,customer_address,NULL,NULL "
        "FROM inbound_event_receipts WHERE provider=? AND provider_message_id=?",
        (event.provider, event.provider_message_id, event.provider, event.provider_message_id),
    ).fetchall()
    if any(row != identity for row in observations):
        raise ValueError("Conflicting Message observation")
    envelopes = connection.execute(
        "SELECT kind,provider_message_id FROM operational_events "
        "WHERE provider=? AND scope_kind='channel' AND scope_id=? AND event_id=? "
        "UNION ALL SELECT 'customer_message',provider_message_id FROM inbound_event_receipts "
        "WHERE provider=? AND channel_id=? AND event_id=?",
        (event.provider, channel, event.metadata.event_id) * 2,
    ).fetchall()
    if any(row != (kind, event.provider_message_id) for row in envelopes):
        raise ValueError("Conflicting Message event identity")
    channels = connection.execute(
        "SELECT messages.recipient_address FROM messages JOIN conversations "
        "ON conversations.id=messages.conversation_id WHERE conversations.provider=? "
        "AND conversations.customer_address=? AND messages.direction='inbound' "
        "UNION SELECT control.channel_id FROM conversation_automation_controls AS control "
        "JOIN conversations ON conversations.id=control.conversation_id "
        "WHERE conversations.provider=? AND conversations.customer_address=? "
        "UNION SELECT channel_id FROM inbound_event_receipts "
        "WHERE provider=? AND customer_address=?",
        (event.provider, event.customer_address) * 3,
    ).fetchall()
    if channels and channels != [(channel,)]:
        raise ValueError("Ambiguous Conversation channel")
