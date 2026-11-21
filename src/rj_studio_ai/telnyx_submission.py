"""Telnyx submission assessment inside the store's existing SQLite transaction."""

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.whatsapp_policy import (
    ConsentEvidence,
    EligibilityDecision,
    EligibilityKind,
    InboundWindowEvidence,
    evaluate_free_form,
    payload_fingerprint,
)


class RetryEvidence(StrEnum):
    NOT_SUBMITTED = "not_submitted"


@dataclass(frozen=True, slots=True)
class SubmissionAssessment:
    decision: EligibilityDecision
    submission_key: str | None = field(default=None, repr=False)

    @property
    def eligible(self) -> bool:
        return self.decision.eligible


def _time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
        return (
            parsed.astimezone(UTC)
            if parsed is not None and parsed.utcoffset() is not None
            else None
        )
    except (ValueError, OverflowError):
        return None


def _deny(reason: str, kind: EligibilityKind = EligibilityKind.UNPROVEN) -> SubmissionAssessment:
    return SubmissionAssessment(EligibilityDecision(kind, reason))


def assess_submission(
    connection: sqlite3.Connection,
    *,
    delivery_id: int,
    owner_token: str,
    message: OutboundMessage | None,
    now: datetime,
) -> SubmissionAssessment:
    """Assess all gates; the caller owns BEGIN IMMEDIATE and the submission CAS."""
    clock = connection.execute(
        "SELECT checked_at FROM telnyx_policy_clock WHERE singleton=1"
    ).fetchone()
    high_water = _time(clock[0]) if clock else None
    if clock and (high_water is None or now < high_water):
        return _deny("clock_unproven")
    connection.execute(
        "INSERT INTO telnyx_policy_clock(singleton,checked_at) VALUES(1,?) "
        "ON CONFLICT(singleton) DO UPDATE SET checked_at=excluded.checked_at",
        (now.isoformat(),),
    )
    cursor = connection.execute(
        """SELECT delivery.*, outbound.body, outbound.conversation_id,
            outbound.in_reply_to_message_id, inbound.provider AS inbound_provider,
            inbound.recipient_address AS inbound_channel,
            conversation.provider AS conversation_provider,
            conversation.customer_address,
            processing.state AS processing_state, processing.automation_revision,
            control.paused, control.revision AS control_revision,
            handoff.active AS handoff_active, handoff.owner_token AS handoff_owner,
            attempt.outcome AS attempt_outcome, attempt.submission_started_at AS attempt_marker
        FROM outbound_deliveries AS delivery
        JOIN messages AS outbound ON outbound.id=delivery.outbound_message_id
        JOIN messages AS inbound ON inbound.id=outbound.in_reply_to_message_id
        JOIN conversations AS conversation ON conversation.id=outbound.conversation_id
        JOIN message_processing AS processing ON processing.inbound_message_id=inbound.id
        LEFT JOIN conversation_automation_controls AS control
          ON control.conversation_id=outbound.conversation_id
        LEFT JOIN conversation_handoffs AS handoff
          ON handoff.conversation_id=outbound.conversation_id
        LEFT JOIN delivery_attempts AS attempt ON attempt.outbound_delivery_id=delivery.id
          AND attempt.attempt_number=delivery.attempt_count
          AND attempt.owner_token=delivery.owner_token
        WHERE delivery.id=?""",
        (delivery_id,),
    )
    values = cursor.fetchone()
    if values is None:
        return _deny("delivery_unavailable")
    row = dict(zip((item[0] for item in cursor.description), values, strict=True))
    if row["provider"] != "telnyx":
        return _deny("provider_mismatch")
    if not connection.execute(
        "SELECT 1 FROM eligible_telnyx_channels WHERE channel_id=?",
        (row["provider_channel_id"],),
    ).fetchone():
        return _deny("channel_unverified", EligibilityKind.CHANNEL_BLOCKED)
    if row["state"] == "unknown":
        return _deny("outcome_unknown", EligibilityKind.OPERATIONAL_UNKNOWN)
    if row["first_submission_at"] is not None:
        return _deny("submission_already_started")
    if (
        row["state"] != "sending"
        or row["owner_token"] != owner_token
        or not owner_token
        or (_time(row["lease_expires_at"]) or datetime.min.replace(tzinfo=UTC)) <= now
        or row["attempt_outcome"] != "started"
        or row["submission_started_at"] is not None
        or row["attempt_marker"] is not None
        or row["processing_state"] != "completed"
    ):
        return _deny("attempt_not_authorized")
    if (
        row["inbound_provider"] != "telnyx"
        or row["conversation_provider"] != "telnyx"
        or row["provider_channel_id"] != row["inbound_channel"]
        or row["recipient_address"] != row["customer_address"]
    ):
        return _deny("identity_mismatch")
    if not re.fullmatch(r"\+[1-9][0-9]{6,14}", row["recipient_address"]):
        return _deny("recipient_unproven")
    if row["paused"] or (
        row["control_revision"] is not None
        and row["control_revision"] != row["automation_revision"]
    ):
        return _deny("conversation_paused")
    if (row["handoff_token"] is None and row["handoff_active"] == 1) or (
        row["handoff_token"] is not None
        and (row["handoff_active"] != 1 or row["handoff_token"] != row["handoff_owner"])
    ):
        return _deny("handoff_blocks_submission")
    if connection.execute(
        """SELECT 1 FROM outbound_deliveries AS conflict
        JOIN messages AS prior ON prior.id=conflict.outbound_message_id
        WHERE prior.conversation_id=? AND conflict.status_conflict=1 LIMIT 1""",
        (row["conversation_id"],),
    ).fetchone():
        return _deny("delivery_conflict", EligibilityKind.OPERATIONAL_UNKNOWN)
    if connection.execute(
        """SELECT 1 FROM messages AS prior
        JOIN message_processing AS processing ON processing.inbound_message_id=prior.id
        LEFT JOIN messages AS reply ON reply.in_reply_to_message_id=prior.id
          AND reply.direction='outbound'
        LEFT JOIN outbound_deliveries AS delivery ON delivery.outbound_message_id=reply.id
        WHERE prior.conversation_id=? AND prior.direction='inbound' AND prior.id<?
          AND (processing.state NOT IN ('completed','suppressed') OR (processing.state='completed'
          AND (delivery.id IS NULL OR delivery.status_conflict=1 OR delivery.state NOT IN
          ('accepted','sent','delivered','read','accepted_legacy','cancelled')))) LIMIT 1""",
        (row["conversation_id"], row["in_reply_to_message_id"]),
    ).fetchone():
        return _deny("ordering_barrier", EligibilityKind.OPERATIONAL_UNKNOWN)
    history = connection.execute(
        """SELECT COUNT(*), COUNT(CASE WHEN outcome='retryable'
            AND retry_evidence='not_submitted' AND submission_started_at IS NULL THEN 1 END)
        FROM delivery_attempts WHERE outbound_delivery_id=? AND attempt_number<?""",
        (delivery_id, row["attempt_count"]),
    ).fetchone()
    # Unique positive attempt numbers plus the exact count prove continuity.
    # Missing historical attempts must never become an empty successful proof.
    expected = row["attempt_count"] - 1
    if history != (expected, expected):
        return _deny("historical_submission_unproven", EligibilityKind.OPERATIONAL_UNKNOWN)
    try:
        key = UUID(row["submission_key"])
    except (ValueError, TypeError, AttributeError):
        return _deny("submission_identity_unproven")
    if key.version != 4 or str(key) != row["submission_key"]:
        return _deny("submission_identity_unproven")
    durable = OutboundMessage(
        row["provider_channel_id"],
        row["recipient_address"],
        row["body"],
        submission_key=row["submission_key"],
    )
    if (message is not None and message != durable) or payload_fingerprint(durable) != row[
        "payload_fingerprint"
    ]:
        return _deny("key_payload_conflict")
    consent_row = connection.execute(
        "SELECT evidence_ref,granted_at,expires_at,revoked_at FROM telnyx_consent "
        "WHERE channel_id=? AND customer_address=?",
        (row["provider_channel_id"], row["recipient_address"]),
    ).fetchone()
    consent = None
    if consent_row is not None:
        # An invalid revocation timestamp still represents revocation, never no revocation.
        consent = ConsentEvidence(
            row["provider_channel_id"],
            row["recipient_address"],
            consent_row[0],
            _time(consent_row[1]),
            _time(consent_row[2]),
            None if consent_row[3] is None else (_time(consent_row[3]) or now),
        )
    receipts = connection.execute(
        """SELECT message_occurred_at,occurred_at,received_at FROM inbound_event_receipts AS receipt
        WHERE provider='telnyx' AND channel_id=? AND customer_address=?
          AND NOT EXISTS (SELECT 1 FROM inbound_event_receipts AS first
            WHERE first.provider=receipt.provider
            AND first.provider_message_id=receipt.provider_message_id
            AND first.id<receipt.id)""",
        (row["provider_channel_id"], row["recipient_address"]),
    ).fetchall()
    decision = evaluate_free_form(
        channel_id=row["provider_channel_id"],
        customer_address=row["recipient_address"],
        evidence=tuple(
            InboundWindowEvidence(*(_time(value) for value in receipt)) for receipt in receipts
        ),
        consent=consent,
        now=now,
        high_water=high_water,
    )
    return SubmissionAssessment(decision, row["submission_key"] if decision.eligible else None)
