"""Preserve intake episodes while adding bounded conversational preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0011_conversational_intake"
down_revision = "0010_appointment_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("appointment_intakes", recreate="always") as batch:
        batch.add_column(sa.Column("preferred_day", sa.Text()))
        batch.add_column(
            sa.Column("request_kind", sa.Text(), nullable=False, server_default="interest")
        )
        batch.add_column(
            sa.Column("recovery_offered", sa.Integer(), nullable=False, server_default="0")
        )
        batch.drop_constraint("ck_intake_questions", type_="check")
        batch.drop_constraint("ck_intake_lifecycle", type_="check")
        batch.create_check_constraint(
            "ck_intake_questions",
            "typeof(clarification_count) = 'integer' AND clarification_count BETWEEN 0 AND 3",
        )
        batch.create_check_constraint(
            "ck_intake_lifecycle",
            "(state = 'collecting' AND handoff_token IS NULL "
            "AND clarification_count BETWEEN 1 AND 3 "
            "AND awaiting_field IN ('desired_service', 'preferred_day', "
            "'preferred_time', 'cancellation_choice') AND awaiting_field IS NOT NULL) OR "
            "(state IN ('handoff', 'released') AND handoff_token IS NOT NULL "
            "AND length(trim(handoff_token)) > 0 AND awaiting_field IS NULL)",
        )
        batch.create_check_constraint(
            "ck_intake_preferred_day",
            "preferred_day IS NULL OR (length(preferred_day) BETWEEN 1 AND 120 "
            "AND preferred_day = trim(preferred_day))",
        )
        batch.create_check_constraint(
            "ck_intake_request_kind", "request_kind IN ('interest', 'cancellation', 'reschedule')"
        )
        batch.create_check_constraint(
            "ck_intake_recovery",
            "typeof(recovery_offered) = 'integer' AND recovery_offered IN (0, 1) "
            "AND (awaiting_field IS NULL OR awaiting_field != 'cancellation_choice' "
            "OR (request_kind = 'cancellation' AND recovery_offered = 1))",
        )


def downgrade() -> None:
    raise RuntimeError("Intake downgrade requires an explicit backup/restore plan")
