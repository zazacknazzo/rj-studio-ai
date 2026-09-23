"""Add durable Outbound Delivery and attempt evidence.

Revision ID: 0007_durable_outbox
Revises: 0006_conversation_context_index
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_durable_outbox"
down_revision: str | None = "0006_conversation_context_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DELIVERY_STATES = (
    "'pending', 'sending', 'retryable', 'unknown', 'accepted', "
    "'sent', 'delivered', 'read', 'failed', 'cancelled', 'accepted_legacy'"
)
ATTEMPT_OUTCOMES = "'started', 'accepted', 'retryable', 'unknown', 'failed'"


def upgrade() -> None:
    connection = op.get_bind()
    orphan_reply_count = int(
        connection.exec_driver_sql(
            """
            SELECT COUNT(*)
            FROM messages AS outbound
            LEFT JOIN messages AS inbound
              ON inbound.id = outbound.in_reply_to_message_id
             AND inbound.direction = 'inbound'
             AND inbound.conversation_id = outbound.conversation_id
             AND inbound.provider = outbound.provider
            WHERE outbound.direction = 'outbound'
              AND inbound.id IS NULL
            """
        ).scalar_one()
    )
    if orphan_reply_count:
        raise RuntimeError("Outbound Message without a valid inbound Message cannot be migrated")

    op.create_table(
        "outbound_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "outbound_message_id",
            sa.Integer(),
            sa.ForeignKey("messages.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_channel_id", sa.Text(), nullable=False),
        sa.Column("recipient_address", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("owner_token", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("safe_error_code", sa.Text(), nullable=True),
        sa.Column("accepted_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            f"state IN ({DELIVERY_STATES})",
            name="ck_outbound_deliveries_state",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_outbound_deliveries_attempt_count",
        ),
        sa.CheckConstraint(
            "(state = 'sending' AND owner_token IS NOT NULL "
            "AND length(trim(owner_token)) > 0 AND lease_expires_at IS NOT NULL) "
            "OR (state != 'sending' AND owner_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_outbound_deliveries_claim_shape",
        ),
        sa.CheckConstraint(
            "(state IN ('pending', 'retryable') AND next_attempt_at IS NOT NULL) "
            "OR (state NOT IN ('pending', 'retryable') AND next_attempt_at IS NULL)",
            name="ck_outbound_deliveries_schedule_shape",
        ),
        sa.CheckConstraint(
            "state NOT IN ('accepted', 'sent', 'delivered', 'read') "
            "OR (provider_message_id IS NOT NULL "
            "AND length(trim(provider_message_id)) > 0)",
            name="ck_outbound_deliveries_provider_id_shape",
        ),
        sa.CheckConstraint(
            "(state IN ('accepted', 'sent', 'delivered', 'read', 'accepted_legacy') "
            "AND accepted_at IS NOT NULL) "
            "OR (state IN ('pending', 'sending', 'retryable', 'unknown', 'cancelled') "
            "AND accepted_at IS NULL) "
            "OR state = 'failed'",
            name="ck_outbound_deliveries_acceptance_shape",
        ),
        sa.CheckConstraint(
            "state NOT IN ('retryable', 'unknown', 'failed') "
            "OR (safe_error_code IS NOT NULL AND length(trim(safe_error_code)) > 0)",
            name="ck_outbound_deliveries_error_shape",
        ),
    )
    op.create_index(
        "uq_outbound_deliveries_provider_message",
        "outbound_deliveries",
        ["provider", "provider_message_id"],
        unique=True,
        sqlite_where=sa.text("provider_message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_outbound_deliveries_due",
        "outbound_deliveries",
        ["state", "next_attempt_at", "id"],
    )
    op.create_index(
        "ix_outbound_deliveries_stale",
        "outbound_deliveries",
        ["state", "lease_expires_at", "id"],
    )
    op.create_index(
        "ix_messages_conversation_direction_id",
        "messages",
        ["conversation_id", "direction", "id"],
    )

    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "outbound_delivery_id",
            sa.Integer(),
            sa.ForeignKey("outbound_deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("owner_token", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("safe_error_code", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "outbound_delivery_id",
            "attempt_number",
            name="uq_delivery_attempt_number",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_delivery_attempts_attempt_number",
        ),
        sa.CheckConstraint(
            "length(trim(owner_token)) > 0",
            name="ck_delivery_attempts_owner_token",
        ),
        sa.CheckConstraint(
            f"outcome IN ({ATTEMPT_OUTCOMES})",
            name="ck_delivery_attempts_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'started' AND completed_at IS NULL) "
            "OR (outcome != 'started' AND completed_at IS NOT NULL)",
            name="ck_delivery_attempts_completion_shape",
        ),
        sa.CheckConstraint(
            "(outcome = 'started' AND provider_message_id IS NULL "
            "AND safe_error_code IS NULL) "
            "OR (outcome = 'accepted' AND provider_message_id IS NOT NULL "
            "AND length(trim(provider_message_id)) > 0 AND safe_error_code IS NULL) "
            "OR (outcome IN ('retryable', 'unknown', 'failed') "
            "AND provider_message_id IS NULL AND safe_error_code IS NOT NULL "
            "AND length(trim(safe_error_code)) > 0)",
            name="ck_delivery_attempts_evidence_shape",
        ),
    )

    op.execute(
        """
        INSERT INTO outbound_deliveries (
            outbound_message_id,
            provider,
            provider_channel_id,
            recipient_address,
            state,
            owner_token,
            lease_expires_at,
            attempt_count,
            next_attempt_at,
            provider_message_id,
            safe_error_code,
            accepted_at,
            created_at,
            updated_at
        )
        SELECT
            outbound.id,
            outbound.provider,
            inbound.recipient_address,
            conversation.customer_address,
            CASE
                WHEN outbound.provider_message_id IS NOT NULL
                 AND length(trim(outbound.provider_message_id)) > 0
                THEN 'accepted_legacy'
                ELSE 'unknown'
            END,
            NULL,
            NULL,
            0,
            NULL,
            outbound.provider_message_id,
            CASE
                WHEN outbound.provider_message_id IS NOT NULL
                 AND length(trim(outbound.provider_message_id)) > 0
                THEN NULL
                ELSE 'legacy_unverified'
            END,
            CASE
                WHEN outbound.provider_message_id IS NOT NULL
                 AND length(trim(outbound.provider_message_id)) > 0
                THEN outbound.created_at
                ELSE NULL
            END,
            outbound.created_at,
            outbound.created_at
        FROM messages AS outbound
        JOIN messages AS inbound
          ON inbound.id = outbound.in_reply_to_message_id
         AND inbound.conversation_id = outbound.conversation_id
         AND inbound.provider = outbound.provider
        JOIN conversations AS conversation ON conversation.id = outbound.conversation_id
        WHERE outbound.direction = 'outbound'
        """
    )

    op.execute(
        """
        CREATE TRIGGER outbound_delivery_requires_ai_reply_insert
        BEFORE INSERT ON outbound_deliveries
        WHEN NOT EXISTS (
            SELECT 1
            FROM messages AS outbound
            JOIN messages AS inbound
              ON inbound.id = outbound.in_reply_to_message_id
             AND inbound.conversation_id = outbound.conversation_id
             AND inbound.provider = outbound.provider
            JOIN conversations AS conversation
              ON conversation.id = outbound.conversation_id
            WHERE outbound.id = NEW.outbound_message_id
              AND outbound.direction = 'outbound'
              AND inbound.direction = 'inbound'
              AND NEW.provider = outbound.provider
              AND NEW.provider_channel_id = inbound.recipient_address
              AND NEW.recipient_address = conversation.customer_address
        )
        BEGIN
            SELECT RAISE(ABORT, 'Outbound Delivery requires a valid AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbound_delivery_requires_ai_reply_update
        BEFORE UPDATE OF outbound_message_id ON outbound_deliveries
        WHEN NOT EXISTS (
            SELECT 1
            FROM messages AS outbound
            JOIN messages AS inbound
              ON inbound.id = outbound.in_reply_to_message_id
             AND inbound.conversation_id = outbound.conversation_id
             AND inbound.provider = outbound.provider
            JOIN conversations AS conversation
              ON conversation.id = outbound.conversation_id
            WHERE outbound.id = NEW.outbound_message_id
              AND outbound.direction = 'outbound'
              AND inbound.direction = 'inbound'
              AND NEW.provider = outbound.provider
              AND NEW.provider_channel_id = inbound.recipient_address
              AND NEW.recipient_address = conversation.customer_address
        )
        BEGIN
            SELECT RAISE(ABORT, 'Outbound Delivery requires a valid AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbound_delivery_protects_message_identity
        BEFORE UPDATE OF
            conversation_id, provider, direction, in_reply_to_message_id
        ON messages
        WHEN (
                NEW.conversation_id IS NOT OLD.conversation_id
             OR NEW.provider IS NOT OLD.provider
             OR NEW.direction IS NOT OLD.direction
             OR NEW.in_reply_to_message_id IS NOT OLD.in_reply_to_message_id
             )
         AND (
                EXISTS (
                    SELECT 1 FROM outbound_deliveries AS delivery
                    WHERE delivery.outbound_message_id = OLD.id
                )
             OR EXISTS (
                    SELECT 1
                    FROM outbound_deliveries AS delivery
                    JOIN messages AS outbound
                      ON outbound.id = delivery.outbound_message_id
                    WHERE outbound.in_reply_to_message_id = OLD.id
                )
             )
        BEGIN
            SELECT RAISE(ABORT, 'Outbound Delivery Message identity is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_requires_delivery_insert
        BEFORE INSERT ON message_processing
        WHEN NEW.state = 'completed'
         AND NOT EXISTS (
            SELECT 1
            FROM messages AS outbound
            JOIN outbound_deliveries AS delivery
              ON delivery.outbound_message_id = outbound.id
            WHERE outbound.in_reply_to_message_id = NEW.inbound_message_id
              AND outbound.direction = 'outbound'
         )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires an Outbound Delivery');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_requires_delivery_update
        BEFORE UPDATE OF state, inbound_message_id ON message_processing
        WHEN NEW.state = 'completed'
         AND NOT EXISTS (
            SELECT 1
            FROM messages AS outbound
            JOIN outbound_deliveries AS delivery
              ON delivery.outbound_message_id = outbound.id
            WHERE outbound.in_reply_to_message_id = NEW.inbound_message_id
              AND outbound.direction = 'outbound'
         )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires an Outbound Delivery');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_protects_delivery_delete
        BEFORE DELETE ON outbound_deliveries
        WHEN EXISTS (
            SELECT 1
            FROM messages AS outbound
            JOIN message_processing AS processing
              ON processing.inbound_message_id = outbound.in_reply_to_message_id
            WHERE outbound.id = OLD.outbound_message_id
              AND processing.state = 'completed'
        )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires its Outbound Delivery');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbound_delivery_identity_is_immutable
        BEFORE UPDATE OF
            outbound_message_id, provider, provider_channel_id,
            recipient_address, created_at
        ON outbound_deliveries
        WHEN NEW.outbound_message_id IS NOT OLD.outbound_message_id
          OR NEW.provider IS NOT OLD.provider
          OR NEW.provider_channel_id IS NOT OLD.provider_channel_id
          OR NEW.recipient_address IS NOT OLD.recipient_address
          OR NEW.created_at IS NOT OLD.created_at
        BEGIN
            SELECT RAISE(ABORT, 'Outbound Delivery identity is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbound_delivery_acceptance_evidence_is_immutable
        BEFORE UPDATE OF provider_message_id, accepted_at ON outbound_deliveries
        WHEN (OLD.provider_message_id IS NOT NULL
              AND NEW.provider_message_id IS NOT OLD.provider_message_id)
          OR (OLD.accepted_at IS NOT NULL AND NEW.accepted_at IS NOT OLD.accepted_at)
        BEGIN
            SELECT RAISE(ABORT, 'Outbound Delivery acceptance evidence is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbound_delivery_state_transition
        BEFORE UPDATE OF state ON outbound_deliveries
        WHEN OLD.state != NEW.state
         AND NOT (
                (OLD.state = 'pending' AND NEW.state IN ('sending', 'cancelled'))
             OR (OLD.state = 'retryable' AND NEW.state IN ('sending', 'cancelled'))
             OR (OLD.state = 'sending'
                 AND NEW.state IN ('accepted', 'retryable', 'unknown', 'failed'))
             OR (OLD.state = 'accepted'
                 AND NEW.state IN ('sent', 'delivered', 'read', 'failed'))
             OR (OLD.state = 'sent' AND NEW.state IN ('delivered', 'read', 'failed'))
             OR (OLD.state = 'delivered' AND NEW.state IN ('read', 'failed'))
             OR (OLD.state = 'unknown'
                 AND OLD.safe_error_code = 'legacy_unverified'
                 AND NEW.state IN ('accepted_legacy', 'cancelled'))
         )
        BEGIN
            SELECT RAISE(ABORT, 'invalid Outbound Delivery state transition');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER delivery_attempt_requires_current_claim
        BEFORE INSERT ON delivery_attempts
        WHEN NOT EXISTS (
            SELECT 1 FROM outbound_deliveries AS delivery
            WHERE delivery.id = NEW.outbound_delivery_id
              AND delivery.state = 'sending'
              AND delivery.owner_token = NEW.owner_token
              AND delivery.attempt_count = NEW.attempt_number
        )
        BEGIN
            SELECT RAISE(ABORT, 'Delivery Attempt requires the current delivery claim');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER delivery_attempt_finalization_requires_current_claim
        BEFORE UPDATE OF outcome, provider_message_id, safe_error_code, completed_at
        ON delivery_attempts
        WHEN OLD.outcome = 'started'
         AND NEW.outcome != 'started'
         AND NOT EXISTS (
            SELECT 1
            FROM outbound_deliveries AS delivery
            WHERE delivery.id = OLD.outbound_delivery_id
              AND delivery.state = 'sending'
              AND delivery.owner_token = OLD.owner_token
              AND delivery.attempt_count = OLD.attempt_number
              AND (
                    (
                        NEW.outcome = 'unknown'
                        AND NEW.safe_error_code = 'sending_lease_expired'
                        AND delivery.lease_expires_at <= NEW.completed_at
                    )
                    OR delivery.lease_expires_at > NEW.completed_at
              )
         )
        BEGIN
            SELECT RAISE(ABORT, 'Delivery Attempt finalization requires current claim');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER delivery_attempt_identity_is_immutable
        BEFORE UPDATE OF
            outbound_delivery_id, attempt_number, owner_token, started_at
        ON delivery_attempts
        WHEN NEW.outbound_delivery_id IS NOT OLD.outbound_delivery_id
          OR NEW.attempt_number IS NOT OLD.attempt_number
          OR NEW.owner_token IS NOT OLD.owner_token
          OR NEW.started_at IS NOT OLD.started_at
        BEGIN
            SELECT RAISE(ABORT, 'Delivery Attempt identity is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER terminal_delivery_attempt_is_immutable
        BEFORE UPDATE OF
            outbound_delivery_id, attempt_number, owner_token, outcome,
            provider_message_id, safe_error_code, started_at, completed_at
        ON delivery_attempts
        WHEN OLD.outcome != 'started'
         AND (
                NEW.outbound_delivery_id IS NOT OLD.outbound_delivery_id
             OR NEW.attempt_number IS NOT OLD.attempt_number
             OR NEW.owner_token IS NOT OLD.owner_token
             OR NEW.outcome IS NOT OLD.outcome
             OR NEW.provider_message_id IS NOT OLD.provider_message_id
             OR NEW.safe_error_code IS NOT OLD.safe_error_code
             OR NEW.started_at IS NOT OLD.started_at
             OR NEW.completed_at IS NOT OLD.completed_at
         )
        BEGIN
            SELECT RAISE(ABORT, 'terminal Delivery Attempt is immutable');
        END
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    unsafe_count = int(
        connection.exec_driver_sql(
            """
            SELECT COUNT(*) FROM outbound_deliveries
            WHERE state != 'accepted_legacy'
            """
        ).scalar_one()
    )
    if unsafe_count:
        raise RuntimeError("Downgrade is blocked while non-legacy Outbound Deliveries exist")
    op.execute("DROP TRIGGER terminal_delivery_attempt_is_immutable")
    op.execute("DROP TRIGGER delivery_attempt_identity_is_immutable")
    op.execute("DROP TRIGGER delivery_attempt_finalization_requires_current_claim")
    op.execute("DROP TRIGGER delivery_attempt_requires_current_claim")
    op.execute("DROP TRIGGER outbound_delivery_state_transition")
    op.execute("DROP TRIGGER outbound_delivery_acceptance_evidence_is_immutable")
    op.execute("DROP TRIGGER outbound_delivery_identity_is_immutable")
    op.execute("DROP TRIGGER completed_processing_protects_delivery_delete")
    op.execute("DROP TRIGGER completed_processing_requires_delivery_update")
    op.execute("DROP TRIGGER completed_processing_requires_delivery_insert")
    op.execute("DROP TRIGGER outbound_delivery_protects_message_identity")
    op.execute("DROP TRIGGER outbound_delivery_requires_ai_reply_update")
    op.execute("DROP TRIGGER outbound_delivery_requires_ai_reply_insert")
    op.drop_table("delivery_attempts")
    op.drop_index("ix_outbound_deliveries_stale", table_name="outbound_deliveries")
    op.drop_index("ix_outbound_deliveries_due", table_name="outbound_deliveries")
    op.drop_index("ix_messages_conversation_direction_id", table_name="messages")
    op.drop_index(
        "uq_outbound_deliveries_provider_message",
        table_name="outbound_deliveries",
    )
    op.drop_table("outbound_deliveries")
