"""Allow paused/no-question intake without consuming a clarification."""

from alembic import op

revision = "0012_agentic_intake"
down_revision = "0011_conversational_intake"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("appointment_intakes", recreate="always") as batch:
        batch.drop_constraint("ck_intake_lifecycle", type_="check")
        batch.create_check_constraint(
            "ck_intake_lifecycle",
            "(state = 'collecting' AND handoff_token IS NULL "
            "AND clarification_count BETWEEN 0 AND 3 "
            "AND (awaiting_field IS NULL OR (clarification_count BETWEEN 1 AND 3 "
            "AND awaiting_field IN ('desired_service', 'preferred_day', 'preferred_time', "
            "'professional_preference', 'cancellation_choice')))) OR "
            "(state IN ('handoff', 'released') AND handoff_token IS NOT NULL "
            "AND length(trim(handoff_token)) > 0 AND awaiting_field IS NULL)",
        )


def downgrade():
    raise RuntimeError("Intake downgrade requires an explicit backup/restore plan")
