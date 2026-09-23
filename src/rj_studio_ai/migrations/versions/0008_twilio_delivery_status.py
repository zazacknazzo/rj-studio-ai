"""Add a durable inbox for early provider delivery statuses.

Revision ID: 0008_twilio_delivery_status
Revises: 0007_durable_outbox
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_twilio_delivery_status"
down_revision: str | None = "0007_durable_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_delivery_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("safe_error_code", sa.Text(), nullable=True),
        sa.Column("received_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "provider",
            "provider_message_id",
            name="uq_pending_delivery_status_provider_message",
        ),
        sa.CheckConstraint(
            "status IN ('sent', 'delivered', 'read', 'failed')",
            name="ck_pending_delivery_status_state",
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND safe_error_code IS NOT NULL "
            "AND length(trim(safe_error_code)) > 0) "
            "OR (status != 'failed' AND safe_error_code IS NULL)",
            name="ck_pending_delivery_status_error_shape",
        ),
    )

    op.execute("DROP TRIGGER outbound_delivery_state_transition")
    op.execute(_state_transition_trigger(allow_read_failure=True))


def downgrade() -> None:
    connection = op.get_bind()
    pending_count = int(
        connection.exec_driver_sql("SELECT COUNT(*) FROM pending_delivery_statuses").scalar_one()
    )
    if pending_count:
        raise RuntimeError("Downgrade is blocked while pending delivery status evidence exists")
    op.execute("DROP TRIGGER outbound_delivery_state_transition")
    op.execute(_state_transition_trigger(allow_read_failure=False))
    op.drop_table("pending_delivery_statuses")


def _state_transition_trigger(*, allow_read_failure: bool) -> str:
    read_transition = (
        " OR (OLD.state = 'read' AND NEW.state = 'failed')" if allow_read_failure else ""
    )
    return f"""
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
             {read_transition}
             OR (OLD.state = 'unknown'
                 AND OLD.safe_error_code = 'legacy_unverified'
                 AND NEW.state IN ('accepted_legacy', 'cancelled'))
         )
        BEGIN
            SELECT RAISE(ABORT, 'invalid Outbound Delivery state transition');
        END
    """
