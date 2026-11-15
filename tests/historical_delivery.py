"""Seed pre-Ticket-08 outboxes without running current SQL against an old schema."""

import sqlite3
from datetime import timedelta


def seed_reply(path, now, *, sending=False, handoff=False):
    timestamp = now.isoformat()
    state = "unknown" if handoff else "pending"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO messages (id,conversation_id,provider,direction,body,created_at,"
            "in_reply_to_message_id) VALUES (2,1,'synthetic','outbound','Synthetic reply',?,1)",
            (timestamp,),
        )
        connection.execute(
            "INSERT INTO outbound_deliveries (id,outbound_message_id,provider,"
            "provider_channel_id,recipient_address,state,next_attempt_at,safe_error_code,"
            "created_at,updated_at,handoff_token) "
            "VALUES (1,2,'synthetic','studio','customer',?,?,?,?,?,?)",
            (
                state,
                None if handoff else timestamp,
                "legacy_unverified" if handoff else None,
                timestamp,
                timestamp,
                "historical-handoff" if handoff else None,
            ),
        )
        connection.execute("UPDATE message_processing SET state='completed',attempt_count=1")
        if handoff:
            connection.execute(
                "INSERT INTO conversation_handoffs VALUES "
                "(1,1,'historical-handoff','explicit_human_request',?,NULL)",
                (timestamp,),
            )
        if sending:
            connection.execute(
                "UPDATE outbound_deliveries SET state='sending', next_attempt_at=NULL,"
                "owner_token='historical-owner',lease_expires_at=?,attempt_count=1",
                ((now + timedelta(seconds=30)).isoformat(),),
            )
            connection.execute(
                "INSERT INTO delivery_attempts (outbound_delivery_id,attempt_number,"
                "owner_token,outcome,started_at) VALUES (1,1,'historical-owner','started',?)",
                (timestamp,),
            )
