"""Durable Conversation handoff and a pre-submission cancellation boundary."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_durable_human_handoff"
down_revision: str | None = "0008_twilio_delivery_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A side table avoids rebuilding conversations with foreign_keys=ON, which
    # could cascade-delete existing Messages when SQLite drops the old table.
    op.create_table(
        "conversation_handoffs",
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("owner_token", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.Text(), nullable=False),
        sa.Column("released_at", sa.Text()),
        sa.CheckConstraint("active IN (0, 1)", name="ck_handoff_active"),
        sa.CheckConstraint(
            "length(trim(owner_token)) > 0 AND length(trim(reason_code)) > 0",
            name="ck_handoff_reason_owner",
        ),
        sa.CheckConstraint(
            "(active = 1 AND released_at IS NULL) OR (active = 0 AND released_at IS NOT NULL)",
            name="ck_handoff_release_shape",
        ),
    )
    op.create_index("ix_handoffs_active", "conversation_handoffs", ["active", "conversation_id"])
    op.add_column("outbound_deliveries", sa.Column("handoff_token", sa.Text()))
    op.add_column("outbound_deliveries", sa.Column("submission_started_at", sa.Text()))
    op.create_index(
        "uq_delivery_handoff_confirmation",
        "outbound_deliveries",
        ["handoff_token"],
        unique=True,
        sqlite_where=sa.text("handoff_token IS NOT NULL"),
    )
    # Existing sending/unknown work may already have crossed an external
    # boundary. Never reinterpret it as proven unsent during this upgrade.
    op.execute(
        "UPDATE outbound_deliveries SET submission_started_at = updated_at "
        "WHERE state IN ('sending', 'unknown')"
    )
    op.execute("DROP TRIGGER create_processing_for_inbound_message")
    op.execute("""
        CREATE TRIGGER create_processing_for_inbound_message
        AFTER INSERT ON messages WHEN NEW.direction = 'inbound'
        BEGIN
            INSERT INTO message_processing (
                inbound_message_id, state, owner_token, lease_expires_at,
                attempt_count, created_at, updated_at
            ) VALUES (NEW.id, CASE WHEN EXISTS (
                SELECT 1 FROM conversation_handoffs
                WHERE conversation_id = NEW.conversation_id AND active = 1
            ) THEN 'suppressed' ELSE 'retryable' END,
                NULL, NULL, 0, NEW.created_at, NEW.created_at);
        END
    """)
    op.execute("""
        CREATE TRIGGER ai_reply_rejects_active_handoff
        BEFORE INSERT ON messages
        WHEN NEW.direction = 'outbound' AND EXISTS (
            SELECT 1 FROM conversation_handoffs
            WHERE conversation_id = NEW.conversation_id AND active = 1
        )
        BEGIN SELECT RAISE(ABORT, 'active handoff rejects AI Reply'); END
    """)
    op.execute("""
        CREATE TRIGGER processing_rejects_active_handoff
        BEFORE UPDATE OF state ON message_processing
        WHEN NEW.state = 'processing' AND EXISTS (
            SELECT 1 FROM conversation_handoffs AS handoff
            JOIN messages AS inbound ON inbound.conversation_id = handoff.conversation_id
            WHERE inbound.id = NEW.inbound_message_id AND handoff.active = 1
        )
        BEGIN SELECT RAISE(ABORT, 'active handoff rejects generation'); END
    """)
    op.execute("DROP TRIGGER outbound_delivery_state_transition")
    op.execute("""
        CREATE TRIGGER outbound_delivery_state_transition
        BEFORE UPDATE OF state ON outbound_deliveries
        WHEN OLD.state != NEW.state AND NOT (
            (OLD.state IN ('pending', 'retryable') AND NEW.state IN ('sending', 'cancelled'))
            OR (OLD.state = 'sending'
                AND NEW.state IN ('accepted', 'retryable', 'unknown', 'failed'))
            OR (OLD.state = 'sending' AND NEW.state = 'cancelled'
                AND OLD.submission_started_at IS NULL)
            OR (OLD.state = 'accepted' AND NEW.state IN ('sent', 'delivered', 'read', 'failed'))
            OR (OLD.state = 'sent' AND NEW.state IN ('delivered', 'read', 'failed'))
            OR (OLD.state = 'delivered' AND NEW.state IN ('read', 'failed'))
            OR (OLD.state = 'read' AND NEW.state = 'failed')
            OR (OLD.state = 'unknown' AND OLD.safe_error_code = 'legacy_unverified'
                AND NEW.state IN ('accepted_legacy', 'cancelled'))
        )
        BEGIN SELECT RAISE(ABORT, 'invalid Outbound Delivery state transition'); END
    """)
    op.execute("DROP TRIGGER delivery_attempt_finalization_requires_current_claim")
    op.execute("""
        CREATE TRIGGER delivery_attempt_finalization_requires_current_claim
        BEFORE UPDATE OF outcome, provider_message_id, safe_error_code, completed_at
        ON delivery_attempts
        WHEN OLD.outcome = 'started' AND NEW.outcome != 'started' AND NOT EXISTS (
            SELECT 1 FROM outbound_deliveries AS delivery
            WHERE delivery.id = OLD.outbound_delivery_id AND delivery.state = 'sending'
              AND delivery.owner_token = OLD.owner_token
              AND delivery.attempt_count = OLD.attempt_number
              AND (
                delivery.lease_expires_at > NEW.completed_at
                OR (NEW.outcome = 'unknown' AND NEW.safe_error_code = 'sending_lease_expired'
                    AND delivery.lease_expires_at <= NEW.completed_at)
                OR (NEW.outcome = 'failed'
                    AND NEW.safe_error_code = 'handoff_cancelled_before_submission'
                    AND delivery.submission_started_at IS NULL)
              )
        )
        BEGIN SELECT RAISE(ABORT, 'Delivery Attempt finalization requires current claim'); END
    """)
    op.execute("""
        CREATE TRIGGER submission_evidence_is_immutable
        BEFORE UPDATE OF submission_started_at ON outbound_deliveries
        WHEN OLD.submission_started_at IS NOT NULL
          AND NEW.submission_started_at IS NOT OLD.submission_started_at
          AND NOT (OLD.state = 'retryable' AND NEW.state = 'sending'
                   AND NEW.submission_started_at IS NULL)
        BEGIN SELECT RAISE(ABORT, 'submission evidence is immutable'); END
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Handoff downgrade requires an explicit backup/restore plan; state cannot be lost"
    )
