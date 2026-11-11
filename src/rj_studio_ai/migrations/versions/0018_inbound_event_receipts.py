"""Retain inbound provenance without rebuilding the operational journal or Messages."""

import sqlalchemy as sa
from alembic import op

revision = "0018_inbound_event_receipts"
down_revision = "0017_automation_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_event_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        *(
            sa.Column(name, sa.Text(), nullable=False)
            for name in (
                "provider",
                "channel_id",
                "customer_address",
                "event_id",
                "provider_message_id",
                "occurred_at",
                "received_at",
                "aliases_json",
            )
        ),
        sa.Column("message_occurred_at", sa.Text()),
    )
    op.create_index(
        "uq_inbound_event_scope",
        "inbound_event_receipts",
        ["provider", "channel_id", "event_id"],
        unique=True,
    )
    op.create_index(
        "ix_inbound_event_message", "inbound_event_receipts", ["provider", "provider_message_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Inbound evidence downgrade requires explicit backup/restore")
