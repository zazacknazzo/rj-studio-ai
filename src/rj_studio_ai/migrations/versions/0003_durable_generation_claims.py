"""Add durable per-Message generation processing state.

Revision ID: 0003_durable_generation_claims
Revises: 0002_reply_idempotency
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_durable_generation_claims"
down_revision: str | None = "0002_reply_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_processing",
        sa.Column(
            "inbound_message_id",
            sa.Integer(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("owner_token", sa.Text()),
        sa.Column("lease_expires_at", sa.Text()),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "state IN ('processing', 'retryable', 'completed', 'suppressed')",
            name="ck_message_processing_state",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 2",
            name="ck_message_processing_attempt_count",
        ),
        sa.CheckConstraint(
            """
            (
                state = 'processing'
                AND owner_token IS NOT NULL
                AND length(owner_token) > 0
                AND lease_expires_at IS NOT NULL
                AND attempt_count >= 1
            )
            OR
            (
                state != 'processing'
                AND owner_token IS NULL
                AND lease_expires_at IS NULL
            )
            """,
            name="ck_message_processing_claim_shape",
        ),
        sa.CheckConstraint(
            "state != 'suppressed' OR attempt_count = 0",
            name="ck_message_processing_suppressed_attempts",
        ),
    )
    op.execute(
        """
        CREATE TRIGGER message_processing_requires_inbound_insert
        BEFORE INSERT ON message_processing
        WHEN (
            SELECT direction FROM messages WHERE id = NEW.inbound_message_id
        ) != 'inbound'
        BEGIN
            SELECT RAISE(ABORT, 'message_processing requires an inbound Message');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER message_processing_requires_inbound_update
        BEFORE UPDATE OF inbound_message_id ON message_processing
        WHEN (
            SELECT direction FROM messages WHERE id = NEW.inbound_message_id
        ) != 'inbound'
        BEGIN
            SELECT RAISE(ABORT, 'message_processing requires an inbound Message');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_requires_reply_insert
        BEFORE INSERT ON message_processing
        WHEN NEW.state = 'completed'
         AND NOT EXISTS (
            SELECT 1 FROM messages
            WHERE in_reply_to_message_id = NEW.inbound_message_id
              AND direction = 'outbound'
         )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires an AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_requires_reply_update
        BEFORE UPDATE OF state, inbound_message_id ON message_processing
        WHEN NEW.state = 'completed'
         AND NOT EXISTS (
            SELECT 1 FROM messages
            WHERE in_reply_to_message_id = NEW.inbound_message_id
              AND direction = 'outbound'
         )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires an AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppressed_processing_rejects_reply_insert
        BEFORE INSERT ON messages
        WHEN NEW.direction = 'outbound'
         AND NEW.in_reply_to_message_id IS NOT NULL
         AND EXISTS (
            SELECT 1 FROM message_processing
            WHERE inbound_message_id = NEW.in_reply_to_message_id
              AND state = 'suppressed'
         )
        BEGIN
            SELECT RAISE(ABORT, 'suppressed processing cannot have an AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppressed_processing_rejects_reply_update
        BEFORE UPDATE OF direction, in_reply_to_message_id ON messages
        WHEN NEW.direction = 'outbound'
         AND NEW.in_reply_to_message_id IS NOT NULL
         AND EXISTS (
            SELECT 1 FROM message_processing
            WHERE inbound_message_id = NEW.in_reply_to_message_id
              AND state = 'suppressed'
         )
        BEGIN
            SELECT RAISE(ABORT, 'suppressed processing cannot have an AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppressed_processing_rejects_existing_reply_insert
        BEFORE INSERT ON message_processing
        WHEN NEW.state = 'suppressed'
         AND EXISTS (
            SELECT 1 FROM messages
            WHERE in_reply_to_message_id = NEW.inbound_message_id
              AND direction = 'outbound'
         )
        BEGIN
            SELECT RAISE(ABORT, 'suppressed processing cannot have an AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppressed_processing_rejects_existing_reply_update
        BEFORE UPDATE OF state, inbound_message_id ON message_processing
        WHEN NEW.state = 'suppressed'
         AND EXISTS (
            SELECT 1 FROM messages
            WHERE in_reply_to_message_id = NEW.inbound_message_id
              AND direction = 'outbound'
         )
        BEGIN
            SELECT RAISE(ABORT, 'suppressed processing cannot have an AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER terminal_processing_state_is_immutable
        BEFORE UPDATE OF state ON message_processing
        WHEN OLD.state IN ('completed', 'suppressed')
         AND NEW.state != OLD.state
        BEGIN
            SELECT RAISE(ABORT, 'terminal processing state is immutable');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_protects_reply_delete
        BEFORE DELETE ON messages
        WHEN OLD.direction = 'outbound'
         AND OLD.in_reply_to_message_id IS NOT NULL
         AND EXISTS (
            SELECT 1 FROM message_processing
            WHERE inbound_message_id = OLD.in_reply_to_message_id
              AND state = 'completed'
         )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires its persisted AI Reply');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER completed_processing_protects_reply_update
        BEFORE UPDATE OF direction, body, in_reply_to_message_id ON messages
        WHEN OLD.direction = 'outbound'
         AND OLD.in_reply_to_message_id IS NOT NULL
         AND EXISTS (
            SELECT 1 FROM message_processing
            WHERE inbound_message_id = OLD.in_reply_to_message_id
              AND state = 'completed'
         )
         AND (
            NEW.direction != OLD.direction
            OR NEW.body != OLD.body
            OR NEW.in_reply_to_message_id IS NOT OLD.in_reply_to_message_id
         )
        BEGIN
            SELECT RAISE(ABORT, 'completed processing requires its persisted AI Reply');
        END
        """
    )
    op.execute(
        """
        INSERT INTO message_processing (
            inbound_message_id,
            state,
            owner_token,
            lease_expires_at,
            attempt_count,
            created_at,
            updated_at
        )
        SELECT
            inbound.id,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM messages AS outbound
                    WHERE outbound.in_reply_to_message_id = inbound.id
                      AND outbound.direction = 'outbound'
                ) THEN 'completed'
                ELSE 'retryable'
            END,
            NULL,
            NULL,
            0,
            inbound.created_at,
            inbound.created_at
        FROM messages AS inbound
        WHERE inbound.direction = 'inbound'
        """
    )
    op.execute(
        """
        CREATE TRIGGER create_processing_for_inbound_message
        AFTER INSERT ON messages
        WHEN NEW.direction = 'inbound'
        BEGIN
            INSERT INTO message_processing (
                inbound_message_id,
                state,
                owner_token,
                lease_expires_at,
                attempt_count,
                created_at,
                updated_at
            ) VALUES (
                NEW.id,
                'retryable',
                NULL,
                NULL,
                0,
                NEW.created_at,
                NEW.created_at
            );
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER create_processing_for_inbound_message")
    op.execute("DROP TRIGGER completed_processing_protects_reply_update")
    op.execute("DROP TRIGGER completed_processing_protects_reply_delete")
    op.execute("DROP TRIGGER terminal_processing_state_is_immutable")
    op.execute("DROP TRIGGER suppressed_processing_rejects_existing_reply_update")
    op.execute("DROP TRIGGER suppressed_processing_rejects_existing_reply_insert")
    op.execute("DROP TRIGGER suppressed_processing_rejects_reply_update")
    op.execute("DROP TRIGGER suppressed_processing_rejects_reply_insert")
    op.execute("DROP TRIGGER completed_processing_requires_reply_update")
    op.execute("DROP TRIGGER completed_processing_requires_reply_insert")
    op.execute("DROP TRIGGER message_processing_requires_inbound_update")
    op.execute("DROP TRIGGER message_processing_requires_inbound_insert")
    op.drop_table("message_processing")
