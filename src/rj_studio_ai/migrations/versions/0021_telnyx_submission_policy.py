"""Add durable Telnyx submission identity without rebuilding historical outboxes."""

import hashlib
import json
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0021_telnyx_submission_policy"
down_revision = "0020_channel_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("submission_key", "payload_fingerprint", "first_submission_at"):
        op.add_column("outbound_deliveries", sa.Column(name, sa.Text()))
    for name in ("submission_started_at", "retry_evidence"):
        op.add_column("delivery_attempts", sa.Column(name, sa.Text()))
    op.create_index(
        "uq_delivery_submission_key", "outbound_deliveries", ["submission_key"], unique=True
    )
    op.create_table(
        "telnyx_consent",
        sa.Column("channel_id", sa.Text(), primary_key=True),
        sa.Column("customer_address", sa.Text(), primary_key=True),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text()),
        sa.CheckConstraint("length(trim(evidence_ref))>0", name="ck_telnyx_consent_evidence"),
    )
    op.create_table(
        "telnyx_policy_clock",
        sa.Column("singleton", sa.Integer(), primary_key=True),
        sa.Column("checked_at", sa.Text(), nullable=False),
        sa.CheckConstraint("singleton=1", name="ck_telnyx_policy_clock"),
    )
    connection = op.get_bind()
    for delivery_id, channel, recipient, body in connection.exec_driver_sql(
        "SELECT delivery.id,provider_channel_id,delivery.recipient_address,outbound.body "
        "FROM outbound_deliveries AS delivery JOIN messages AS outbound "
        "ON outbound.id=delivery.outbound_message_id WHERE delivery.provider='telnyx'"
    ).fetchall():
        canonical = json.dumps(
            ["telnyx", "free_form", channel, recipient, body],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        connection.exec_driver_sql(
            "UPDATE outbound_deliveries SET submission_key=?,payload_fingerprint=? WHERE id=?",
            (str(uuid4()), "v1:" + hashlib.sha256(canonical).hexdigest(), delivery_id),
        )
    # Historical markers have no per-attempt proof; do not invent first-submission time.
    op.execute("""CREATE TRIGGER telnyx_submission_identity_insert
        BEFORE INSERT ON outbound_deliveries
        WHEN NEW.provider='telnyx' AND (NEW.submission_key IS NULL OR length(NEW.submission_key)!=36
          OR NEW.payload_fingerprint IS NULL OR length(NEW.payload_fingerprint)!=67)
        BEGIN SELECT RAISE(ABORT,'submission identity required'); END""")
    op.execute("""CREATE TRIGGER telnyx_submission_rejects_replacement
        BEFORE INSERT ON outbound_deliveries
        WHEN EXISTS (SELECT 1 FROM outbound_deliveries WHERE provider='telnyx'
          AND (id=NEW.id OR outbound_message_id=NEW.outbound_message_id
            OR submission_key=NEW.submission_key))
        BEGIN SELECT RAISE(ABORT,'submission identity already exists'); END""")
    op.execute("""CREATE TRIGGER telnyx_submission_identity_immutable
        BEFORE UPDATE ON outbound_deliveries
        WHEN OLD.provider='telnyx' AND (NEW.submission_key IS NOT OLD.submission_key
          OR NEW.payload_fingerprint IS NOT OLD.payload_fingerprint
          OR (OLD.first_submission_at IS NOT NULL
            AND NEW.first_submission_at IS NOT OLD.first_submission_at))
        BEGIN SELECT RAISE(ABORT,'submission identity is immutable'); END""")
    op.execute("""CREATE TRIGGER telnyx_submission_body_immutable
        BEFORE UPDATE OF body,recipient_address ON messages
        WHEN (NEW.body IS NOT OLD.body OR NEW.recipient_address IS NOT OLD.recipient_address)
          AND EXISTS (SELECT 1 FROM outbound_deliveries WHERE provider='telnyx'
            AND (outbound_message_id=OLD.id OR outbound_message_id IN
              (SELECT id FROM messages WHERE in_reply_to_message_id=OLD.id)))
        BEGIN SELECT RAISE(ABORT,'submission payload is immutable'); END""")
    op.execute("""CREATE TRIGGER telnyx_submission_message_replacement BEFORE INSERT ON messages
        WHEN EXISTS (SELECT 1 FROM outbound_deliveries WHERE provider='telnyx'
          AND (outbound_message_id=NEW.id OR outbound_message_id IN
            (SELECT id FROM messages WHERE in_reply_to_message_id=NEW.id)))
        BEGIN SELECT RAISE(ABORT,'submission message already exists'); END""")
    op.execute("""CREATE TRIGGER telnyx_attempt_rejects_replacement
        BEFORE INSERT ON delivery_attempts WHEN EXISTS (
            SELECT 1 FROM delivery_attempts AS attempt
            JOIN outbound_deliveries AS delivery ON delivery.id=attempt.outbound_delivery_id
            WHERE delivery.provider='telnyx' AND (attempt.id=NEW.id
                OR (attempt.outbound_delivery_id=NEW.outbound_delivery_id
                    AND attempt.attempt_number=NEW.attempt_number)
                OR attempt.owner_token=NEW.owner_token))
        BEGIN SELECT RAISE(ABORT,'attempt submission evidence already exists'); END""")
    op.execute("""CREATE TRIGGER telnyx_attempt_initial_evidence
        BEFORE INSERT ON delivery_attempts WHEN EXISTS (
            SELECT 1 FROM outbound_deliveries WHERE id=NEW.outbound_delivery_id
              AND provider='telnyx') AND (
            NEW.submission_started_at IS NOT NULL OR NEW.retry_evidence IS NOT NULL)
        BEGIN SELECT RAISE(ABORT,'new attempt cannot claim prior submission evidence'); END""")
    op.execute("""CREATE TRIGGER telnyx_attempt_evidence_retained
        BEFORE DELETE ON delivery_attempts WHEN EXISTS (
            SELECT 1 FROM outbound_deliveries WHERE id=OLD.outbound_delivery_id
              AND provider='telnyx')
        BEGIN SELECT RAISE(ABORT,'attempt submission evidence retained'); END""")
    op.execute("""CREATE TRIGGER telnyx_attempt_evidence_immutable
        BEFORE UPDATE ON delivery_attempts
        WHEN (OLD.submission_started_at IS NOT NULL
            AND NEW.submission_started_at IS NOT OLD.submission_started_at)
          OR (OLD.retry_evidence IS NOT NULL AND NEW.retry_evidence IS NOT OLD.retry_evidence)
          OR NEW.retry_evidence NOT IN ('not_submitted')
          OR (NEW.retry_evidence IS NOT NULL AND NEW.submission_started_at IS NOT NULL)
        BEGIN SELECT RAISE(ABORT,'attempt submission evidence is immutable'); END""")
    op.execute("""CREATE TRIGGER telnyx_attempt_evidence_requires_current_claim
        BEFORE UPDATE OF submission_started_at,retry_evidence ON delivery_attempts
        WHEN EXISTS (SELECT 1 FROM outbound_deliveries
            WHERE id=OLD.outbound_delivery_id AND provider='telnyx') AND (
          (NEW.submission_started_at IS NOT OLD.submission_started_at AND NOT (
            OLD.outcome='started' AND NEW.outcome='started' AND EXISTS (
              SELECT 1 FROM outbound_deliveries WHERE id=OLD.outbound_delivery_id
                AND state='sending' AND owner_token=OLD.owner_token
                AND attempt_count=OLD.attempt_number
                AND submission_started_at=NEW.submission_started_at)))
          OR (NEW.retry_evidence IS NOT OLD.retry_evidence AND NOT (
            OLD.outcome='started' AND NEW.outcome='retryable'
            AND NEW.submission_started_at IS NULL AND EXISTS (
              SELECT 1 FROM outbound_deliveries WHERE id=OLD.outbound_delivery_id
                AND state='sending' AND owner_token=OLD.owner_token
                AND attempt_count=OLD.attempt_number AND submission_started_at IS NULL))))
        BEGIN SELECT RAISE(ABORT,'attempt evidence requires current claim'); END""")
    op.execute("""CREATE TRIGGER telnyx_retry_requires_proof
        BEFORE UPDATE OF state ON outbound_deliveries
        WHEN NEW.provider='telnyx' AND NEW.state='retryable' AND OLD.state!='retryable'
          AND NOT EXISTS (SELECT 1 FROM delivery_attempts WHERE outbound_delivery_id=NEW.id
            AND attempt_number=NEW.attempt_count AND outcome='retryable'
            AND retry_evidence='not_submitted' AND submission_started_at IS NULL)
        BEGIN SELECT RAISE(ABORT,'retry requires non-submission proof'); END""")
    op.execute("""CREATE TRIGGER telnyx_clock_monotonic BEFORE UPDATE ON telnyx_policy_clock
        WHEN NEW.singleton IS NOT OLD.singleton OR NEW.checked_at<OLD.checked_at
        BEGIN SELECT RAISE(ABORT,'policy clock cannot regress'); END""")
    op.execute("""CREATE TRIGGER telnyx_clock_retained BEFORE DELETE ON telnyx_policy_clock
        BEGIN SELECT RAISE(ABORT,'policy clock retained'); END""")
    op.execute("""CREATE TRIGGER telnyx_clock_replacement BEFORE INSERT ON telnyx_policy_clock
        WHEN EXISTS (SELECT 1 FROM telnyx_policy_clock
          WHERE singleton=NEW.singleton AND checked_at>NEW.checked_at)
        BEGIN SELECT RAISE(ABORT,'policy clock cannot regress'); END""")


def downgrade() -> None:
    raise RuntimeError("Submission policy downgrade requires explicit backup/restore")
