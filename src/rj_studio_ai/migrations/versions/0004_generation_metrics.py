"""Persist privacy-safe LLM generation metrics.

Revision ID: 0004_generation_metrics
Revises: 0003_durable_generation_claims
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_generation_metrics"
down_revision: str | None = "0003_durable_generation_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inbound_message_id",
            sa.Integer(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("configuration", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("estimated_cost_microusd", sa.Integer()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("attempt_number BETWEEN 1 AND 2", name="ck_generation_metrics_attempt"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_generation_metrics_latency"),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure')", name="ck_generation_metrics_outcome"
        ),
        sa.CheckConstraint(
            "(outcome = 'success' AND error_code IS NULL) OR "
            "(outcome = 'failure' AND error_code IS NOT NULL)",
            name="ck_generation_metrics_error_shape",
        ),
        sa.UniqueConstraint(
            "inbound_message_id", "attempt_number", name="uq_generation_metrics_attempt"
        ),
    )


def downgrade() -> None:
    op.drop_table("generation_metrics")
