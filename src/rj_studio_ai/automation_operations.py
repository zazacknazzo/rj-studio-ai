"""Private operational state, independent of Message content and provider identity."""

import json
import re
import sqlite3
from datetime import datetime


class OperationConflict(ValueError):
    pass


def automation_state(connection: sqlite3.Connection, opaque_id: str) -> dict:
    row = connection.execute(
        """SELECT ids.conversation_id, COALESCE(control.paused,0),
        COALESCE(control.revision,0), COALESCE(handoff.active,0)
        FROM conversation_operation_ids AS ids
        LEFT JOIN conversation_automation_controls AS control USING(conversation_id)
        LEFT JOIN conversation_handoffs AS handoff USING(conversation_id)
        WHERE ids.opaque_id=?""",
        (opaque_id,),
    ).fetchone()
    if row is None:
        raise LookupError("conversation_not_found")
    states = connection.execute(
        """SELECT delivery.state, delivery.submission_started_at
        FROM outbound_deliveries AS delivery
        JOIN messages ON messages.id=delivery.outbound_message_id
        WHERE messages.conversation_id=?""",
        (row[0],),
    ).fetchall()
    return dict(
        conversation_id=opaque_id,
        paused=bool(row[1]),
        revision=row[2],
        handoff_active=bool(row[3]),
        in_flight_possible=any(s == "sending" and marker is not None for s, marker in states),
        unresolved_delivery=any(s in ("unknown", "failed") for s, _ in states),
    )


def apply_operation(
    connection, opaque_id, action, operation_id, expected_revision, operator_id, timestamp
):
    if (
        action not in ("pause", "resume")
        or not re.fullmatch("[a-f0-9]{32}", operation_id)
        or not re.fullmatch("[a-f0-9]{32}", opaque_id)
        or not re.fullmatch("[a-zA-Z0-9_-]{1,64}", operator_id)
        or type(expected_revision) is not int
        or not 0 <= expected_revision < 9223372036854775807
    ):
        raise ValueError("invalid_operation")
    state = automation_state(connection, opaque_id)
    conversation_id = connection.execute(
        "SELECT conversation_id FROM conversation_operation_ids WHERE opaque_id=?", (opaque_id,)
    ).fetchone()[0]
    receipt = connection.execute(
        "SELECT conversation_id, operator_id, action, expected_revision, result_json "
        "FROM automation_operation_receipts WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if receipt:
        if receipt[:4] != (conversation_id, operator_id, action, expected_revision):
            raise OperationConflict("operation_key_conflict")
        return json.loads(receipt[4])
    if state["revision"] != expected_revision:
        raise OperationConflict("revision_conflict")
    if action == "resume" and not state["paused"]:
        raise OperationConflict("not_paused")
    channels = connection.execute(
        "SELECT recipient_address FROM messages WHERE conversation_id=? AND direction='inbound' "
        "UNION SELECT channel_id FROM conversation_automation_controls WHERE conversation_id=? "
        "UNION SELECT provider_channel_id FROM outbound_deliveries JOIN messages "
        "ON messages.id=outbound_deliveries.outbound_message_id WHERE conversation_id=?",
        (conversation_id, conversation_id, conversation_id),
    ).fetchall()
    if len(channels) != 1 or not channels[0][0]:
        raise OperationConflict("channel_identity_unresolved")
    previous_times = connection.execute(
        "SELECT updated_at, resumed_at FROM conversation_automation_controls "
        "WHERE conversation_id=?",
        (conversation_id,),
    ).fetchone()
    # A wall-clock correction must never lower the future-only admission cutoff.
    # Revisions, not these times, order concurrent operator/human decisions.
    timestamp = max(
        datetime.fromisoformat(value)
        for value in (timestamp, *(previous_times or ()))
        if value is not None
    ).isoformat()
    connection.execute(
        """INSERT INTO conversation_automation_controls
        (conversation_id,channel_id,paused,revision,updated_at) VALUES (?,?,?,?,?)
        ON CONFLICT(conversation_id) DO UPDATE SET paused=excluded.paused,
        revision=excluded.revision, updated_at=excluded.updated_at""",
        (conversation_id, channels[0][0], int(action == "pause"), expected_revision + 1, timestamp),
    )
    if action == "resume":
        connection.execute(
            "UPDATE conversation_automation_controls SET resumed_at=? WHERE conversation_id=?",
            (timestamp, conversation_id),
        )
    result = automation_state(connection, opaque_id)
    connection.execute(
        "INSERT INTO automation_operation_receipts "
        "(operation_id,conversation_id,operator_id,action,"
        "expected_revision,result_json,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            operation_id,
            conversation_id,
            operator_id,
            action,
            expected_revision,
            json.dumps(result, sort_keys=True),
            timestamp,
        ),
    )
    return result
