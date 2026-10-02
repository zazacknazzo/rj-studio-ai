"""One bounded, replaceable appointment-interest episode per Conversation."""

import sqlalchemy as sa
from alembic import op

revision = "0010_appointment_intake"
down_revision = "0009_durable_human_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointment_intakes",
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("episode_token", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("desired_service", sa.Text()),
        sa.Column("preferred_time", sa.Text()),
        sa.Column("professional_preference", sa.Text()),
        sa.Column("clarification_count", sa.Integer(), nullable=False),
        sa.Column("awaiting_field", sa.Text()),
        # Scalar cursor survives Message retention; it is not a Message foreign key.
        sa.Column("last_inbound_message_id", sa.Integer(), nullable=False),
        sa.Column("handoff_token", sa.Text()),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "state IN ('collecting', 'handoff', 'released')", name="ck_intake_state"
        ),
        sa.CheckConstraint(
            "typeof(clarification_count) = 'integer' AND clarification_count BETWEEN 0 AND 2",
            name="ck_intake_questions",
        ),
        sa.CheckConstraint(
            "length(trim(episode_token)) > 0 AND last_inbound_message_id > 0",
            name="ck_intake_episode",
        ),
        sa.CheckConstraint(
            "(state = 'collecting' AND handoff_token IS NULL "
            "AND clarification_count BETWEEN 1 AND 2 AND awaiting_field IS NOT NULL "
            "AND awaiting_field IN ('desired_service', 'preferred_time')) OR "
            "(state IN ('handoff', 'released') AND handoff_token IS NOT NULL "
            "AND length(trim(handoff_token)) > 0 AND awaiting_field IS NULL)",
            name="ck_intake_lifecycle",
        ),
        *[
            sa.CheckConstraint(
                f"{field} IS NULL OR (length({field}) BETWEEN 1 AND 120 "
                f"AND {field} = trim({field}))",
                name=f"ck_intake_{field}",
            )
            for field in ("desired_service", "preferred_time", "professional_preference")
        ],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Intake downgrade requires an explicit backup/restore plan; preferences cannot be lost"
    )
