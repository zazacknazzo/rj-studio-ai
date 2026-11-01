"""Private operational observations; no changes to messaging or automation state."""

import sqlalchemy as sa
from alembic import op

revision = "0014_operational_event_journal"
down_revision = "0013_openai_generation_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        *(
            sa.Column(name, sa.Text(), nullable=False)
            for name in (
                "provider",
                "scope_kind",
                "scope_id",
                "event_id",
                "kind",
                "origin",
                "occurred_at",
                "received_at",
            )
        ),
        *(
            sa.Column(name, sa.Text())
            for name in (
                "provider_message_id",
                "customer_address",
                "message_occurred_at",
                "original_namespace",
                "original_message_id",
                "availability",
                "reason",
            )
        ),
        sa.CheckConstraint(
            "length(trim(provider)) > 0 AND length(trim(scope_id)) > 0 "
            "AND length(trim(event_id)) > 0",
            name="ck_operational_identity",
        ),
        sa.CheckConstraint("scope_kind IN ('account', 'channel')", name="ck_operational_scope"),
        sa.CheckConstraint(
            "(kind = 'channel_lifecycle' AND origin = 'provider' "
            "AND provider_message_id IS NULL AND customer_address IS NULL "
            "AND message_occurred_at IS NULL AND original_namespace IS NULL "
            "AND original_message_id IS NULL AND availability IS NOT NULL "
            "AND availability IN ('blocked', 'verification_required') "
            "AND reason IS NOT NULL "
            "AND reason IN ('offboarded', 'disconnected', 'reconnected', 'unrecognized')) "
            "OR (kind IN ('human_activity', 'message_edit', 'message_revocation') "
            "AND scope_kind = 'channel' AND provider_message_id IS NOT NULL "
            "AND length(trim(provider_message_id)) > 0 AND customer_address IS NOT NULL "
            "AND length(trim(customer_address)) > 0 AND availability IS NULL AND reason IS NULL "
            "AND ((kind = 'human_activity' AND origin = 'human_operator' "
            "AND original_namespace IS NULL AND original_message_id IS NULL) "
            "OR (kind IN ('message_edit', 'message_revocation') "
            "AND origin IN ('customer', 'human_operator') "
            "AND original_namespace IS NOT NULL AND length(trim(original_namespace)) > 0 "
            "AND original_message_id IS NOT NULL AND length(trim(original_message_id)) > 0)))",
            name="ck_operational_shape",
        ),
    )
    op.create_index(
        "uq_operational_event_scope",
        "operational_events",
        ["provider", "scope_kind", "scope_id", "event_id"],
        unique=True,
    )
    op.create_index(
        "ix_operational_message",
        "operational_events",
        ["provider", "scope_kind", "scope_id", "provider_message_id"],
    )
    op.create_table(
        "operational_event_aliases",
        sa.Column(
            "event_record_id",
            sa.Integer(),
            sa.ForeignKey("operational_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(trim(namespace)) > 0 AND length(trim(message_id)) > 0",
            name="ck_operational_alias_identity",
        ),
    )
    op.create_index(
        "uq_operational_alias",
        "operational_event_aliases",
        ["event_record_id", "namespace", "message_id"],
        unique=True,
    )
    op.create_index(
        "ix_operational_alias_reference",
        "operational_event_aliases",
        ["namespace", "message_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Operational evidence downgrade requires explicit backup/restore")
