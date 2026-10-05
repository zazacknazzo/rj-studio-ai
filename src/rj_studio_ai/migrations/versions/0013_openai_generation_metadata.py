"""Optional allowlisted Responses metrics, preserving all existing generation evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0013_openai_generation_metadata"
down_revision = "0012_agentic_intake"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("cached_input_tokens", "cache_write_tokens", "reasoning_tokens"):
        op.add_column(
            "generation_metrics",
            sa.Column(name, sa.Integer(), sa.CheckConstraint(f"{name} IS NULL OR {name} >= 0")),
        )
    op.add_column(
        "generation_metrics",
        sa.Column(
            "response_status",
            sa.Text(),
            sa.CheckConstraint(
                "response_status IS NULL OR response_status IN ('completed', 'incomplete', "
                "'failed', 'in_progress', 'queued', 'cancelled', 'unrecognized')"
            ),
        ),
    )
    op.add_column(
        "generation_metrics",
        sa.Column(
            "incomplete_reason",
            sa.Text(),
            sa.CheckConstraint(
                "incomplete_reason IS NULL OR incomplete_reason IN ('max_output_tokens', "
                "'content_filter', 'unrecognized')"
            ),
        ),
    )


def downgrade():
    raise RuntimeError("Generation evidence downgrade requires explicit backup/restore")
