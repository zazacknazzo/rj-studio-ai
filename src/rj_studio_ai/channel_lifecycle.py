"""Single-business channel binding and lifecycle effects in the ingress transaction."""

import re
import sqlite3
from dataclasses import dataclass

from rj_studio_ai.domain import ChannelAvailabilityChanged, ChannelScope


@dataclass(frozen=True, slots=True)
class TelnyxChannelBinding:
    waba_id: str
    channel_id: str
    organization_id: str
    profile_id: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\+[1-9][0-9]{1,14}", self.channel_id) or not all(
            re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
            for value in (self.waba_id, self.organization_id, self.profile_id)
        ):
            raise ValueError("Invalid channel binding")


def bind_channel(connection: sqlite3.Connection, binding: TelnyxChannelBinding, timestamp: str):
    values = (binding.waba_id, binding.channel_id, binding.organization_id, binding.profile_id)
    existing = connection.execute(
        "SELECT waba_id,channel_id,organization_id,profile_id FROM channel_lifecycle "
        "WHERE provider='telnyx'"
    ).fetchone()
    if existing is not None and existing != values:
        raise ValueError("Conflicting configured channel binding")
    if existing is None:
        connection.execute(
            "INSERT INTO channel_lifecycle(provider,waba_id,channel_id,organization_id,"
            "profile_id,state,revision,updated_at) "
            "VALUES ('telnyx',?,?,?,?,'verification_required',0,?)",
            (*values, timestamp),
        )
    apply_pending_lifecycle(connection, timestamp)


def validate_lifecycle_scope(connection: sqlite3.Connection, event: ChannelAvailabilityChanged):
    if event.provider != "telnyx" or event.scope is not ChannelScope.ACCOUNT:
        raise ValueError("Invalid lifecycle scope")
    binding = connection.execute(
        "SELECT waba_id FROM channel_lifecycle WHERE provider='telnyx'"
    ).fetchone()
    if binding != (event.scope_id,):
        raise ValueError("Unbound lifecycle account")
    for table in ("inbound_event_receipts", "delivery_status_events", "operational_events"):
        conflict = connection.execute(
            f"SELECT 1 FROM {table} WHERE provider=? AND event_id=? "
            + (
                "AND (kind!='channel_lifecycle' OR scope_kind!='account' OR scope_id!=?) "
                if table == "operational_events"
                else ""
            )
            + "LIMIT 1",
            (event.provider, event.metadata.event_id)
            + ((event.scope_id,) if table == "operational_events" else ()),
        ).fetchone()
        if conflict:
            raise ValueError("Conflicting lifecycle event identity")


def apply_pending_lifecycle(connection: sqlite3.Connection, timestamp: str) -> None:
    # Local journal sequence is receipt order, never a claim about remote chronology.
    events = connection.execute(
        "SELECT event.id,event.availability FROM operational_events AS event "
        "JOIN channel_lifecycle AS channel ON channel.provider=event.provider "
        "AND channel.waba_id=event.scope_id "
        "WHERE event.kind='channel_lifecycle' AND event.scope_kind='account' "
        "AND NOT EXISTS (SELECT 1 FROM channel_lifecycle_effects WHERE event_record_id=event.id) "
        "ORDER BY event.id"
    ).fetchall()
    for event_id, state in events:
        connection.execute(
            "UPDATE channel_lifecycle SET state=?,revision=revision+1,"
            "last_event_record_id=?,updated_at=MAX(updated_at,?) WHERE provider='telnyx'",
            (state, event_id, timestamp),
        )
        connection.execute(
            "INSERT INTO channel_lifecycle_effects(event_record_id) VALUES (?)", (event_id,)
        )


def channel_allows_automation(connection: sqlite3.Connection, provider: str, channel: str) -> bool:
    return (
        provider != "telnyx"
        or connection.execute(
            "SELECT 1 FROM eligible_telnyx_channels WHERE channel_id=?", (channel,)
        ).fetchone()
        is not None
    )
