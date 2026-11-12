"""Scoped status ledger, called only inside the store's short writer transaction."""

import sqlite3
from datetime import UTC

from rj_studio_ai.domain import DeliveryStatus, DeliveryStatusReceived

_COLUMNS = (
    "provider",
    "event_id",
    "provider_message_id",
    "channel_id",
    "customer_address",
    "account_id",
    "profile_id",
    "event_type",
    "recipient_status",
    "status",
    "occurred_at",
)


def validate_status(event: DeliveryStatusReceived) -> None:
    if (
        event.metadata is None
        or event.evidence is None
        or not event.channel_id
        or not event.customer_address
        or event.provider != "telnyx"
        or not isinstance(event.status, DeliveryStatus)
        or event.safe_error_code
        != ("provider_delivery_failed" if event.status is DeliveryStatus.FAILED else None)
    ):
        raise ValueError("Scoped delivery status requires verified provenance")


def _delivery(connection: sqlite3.Connection, provider: str, message_id: str):
    return connection.execute(
        "SELECT id,provider_channel_id,recipient_address,state,status_conflict,accepted_at, "
        "(SELECT owner_token FROM delivery_attempts WHERE outbound_delivery_id=delivery.id "
        "AND outcome='accepted' AND provider_message_id=delivery.provider_message_id) "
        "FROM outbound_deliveries AS delivery WHERE provider=? AND provider_message_id=?",
        (provider, message_id),
    ).fetchone()


def _require_ai_identity(connection, provider, message_id, event_id=None):
    # No lookup through aliases. An inbound/echo identity cannot become an AI delivery.
    for table in ("inbound_event_receipts", "operational_events"):
        row = connection.execute(
            f"SELECT 1 FROM {table} WHERE provider=? "
            "AND (provider_message_id=? OR event_id=?) LIMIT 1",
            (provider, message_id, event_id),
        ).fetchone()
        if row is not None:
            raise ValueError("Conflicting delivery Message identity")
    if connection.execute(
        "SELECT 1 FROM messages WHERE provider=? AND provider_message_id=? AND direction='inbound'",
        (provider, message_id),
    ).fetchone():
        raise ValueError("Conflicting delivery Message identity")


def record_status(connection, event: DeliveryStatusReceived, timestamp: str) -> str:
    validate_status(event)
    metadata, evidence = event.metadata, event.evidence
    _require_ai_identity(connection, event.provider, event.provider_message_id, metadata.event_id)
    values = (
        event.provider,
        metadata.event_id,
        event.provider_message_id,
        event.channel_id,
        event.customer_address,
        evidence.account_id,
        evidence.profile_id,
        evidence.event_type,
        evidence.recipient_status,
        event.status,
        metadata.occurred_at.astimezone(UTC).isoformat(),
    )
    existing = connection.execute(
        f"SELECT {','.join(_COLUMNS)} FROM delivery_status_events WHERE provider=? AND event_id=?",
        values[:2],
    ).fetchone()
    if existing is not None and existing != values:
        raise ValueError("Conflicting delivery event identity")
    scopes = connection.execute(
        "SELECT DISTINCT channel_id,customer_address,account_id,profile_id "
        "FROM delivery_status_events WHERE provider=? AND provider_message_id=?",
        (event.provider, event.provider_message_id),
    ).fetchall()
    if scopes and scopes != [values[3:7]]:
        raise ValueError("Conflicting delivery Message scope")
    delivery = _delivery(connection, event.provider, event.provider_message_id)
    if delivery and delivery[1:3] != (event.channel_id, event.customer_address):
        raise ValueError("Delivery correlation scope mismatch")
    if existing is None:
        connection.execute(
            f"INSERT INTO delivery_status_events ({','.join(_COLUMNS)},received_at) "
            f"VALUES ({','.join('?' for _ in range(len(_COLUMNS) + 1))})",
            (*values, timestamp),
        )
    if delivery is None:
        return "buffered" if existing is None else "ignored"
    changed = reconcile_statuses(connection, event.provider, event.provider_message_id, timestamp)
    return "applied" if changed else "ignored"


def reconcile_statuses(connection, provider: str, message_id: str, timestamp: str) -> bool:
    """Acceptance and receipt linking commit together, or both roll back."""
    _require_ai_identity(connection, provider, message_id)
    delivery = _delivery(connection, provider, message_id)
    if delivery is None:
        return False
    records = connection.execute(
        "SELECT DISTINCT channel_id,customer_address,delivery_id,status,acceptance_token "
        "FROM delivery_status_events "
        "WHERE provider=? AND provider_message_id=?",
        (provider, message_id),
    ).fetchall()
    if any(
        r[:2] != delivery[1:3] or r[2] not in (None, delivery[0]) or r[4] not in (None, delivery[6])
        for r in records
    ):
        raise ValueError("Delivery correlation scope mismatch")
    # A legacy unscoped row cannot be evidence even if its identifier happens to match.
    connection.execute(
        "UPDATE delivery_status_events SET delivery_id=?,acceptance_token=? "
        "WHERE provider=? AND provider_message_id=? AND delivery_id IS NULL",
        (delivery[0], delivery[6], provider, message_id),
    )
    current, conflict = delivery[3:5]
    if delivery[5] is None or current not in ("accepted", "sent", "delivered", "read", "failed"):
        return False
    statuses = {r[3] for r in records}
    if current in ("sent", "delivered", "read", "failed"):
        statuses.add(current)
    success = next((s for s in ("read", "delivered", "sent") if s in statuses), None)
    failed = "failed" in statuses
    conflict = int(bool(conflict or (failed and success in ("delivered", "read"))))
    target = success if conflict else ("failed" if failed else (success or current))
    reason = (
        "provider_status_conflict"
        if conflict
        else ("provider_delivery_failed" if target == "failed" else None)
    )
    if (target, conflict) == delivery[3:5]:
        return False
    connection.execute(
        "UPDATE outbound_deliveries SET state=?, status_conflict=?, safe_error_code=?, "
        "updated_at=MAX(updated_at,?) WHERE id=?",
        (target, conflict, reason, timestamp, delivery[0]),
    )
    return True
