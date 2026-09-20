"""Preserve inbound recipient addresses for manual recovery.

Revision ID: 0005_recovery_recipient_address
Revises: 0004_generation_metrics
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_recovery_recipient_address"
down_revision: str | None = "0004_generation_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("recipient_address", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("recipient_address")
