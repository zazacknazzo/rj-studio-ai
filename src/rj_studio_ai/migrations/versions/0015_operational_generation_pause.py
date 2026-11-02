"""Durable operational pause, separate from policy handoff and outbound delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0015_operational_generation_pause"
down_revision = "0014_operational_event_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite CHECK removal requires a rebuild. This is a leaf table; no other
    # table references it. Keep FK enforcement and all existing trigger bodies.
    connection = op.get_bind()
    triggers = connection.exec_driver_sql(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' "
        "AND sql LIKE '%message_processing%'"
    ).fetchall()
    for name, _ in triggers:
        connection.exec_driver_sql('DROP TRIGGER "' + name.replace('"', '""') + '"')
    with op.batch_alter_table("message_processing", recreate="always") as batch:
        batch.drop_constraint("ck_message_processing_suppressed_attempts", type_="check")
        batch.add_column(
            sa.Column("automation_revision", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_check_constraint(
            "ck_processing_automation_revision", "automation_revision >= 0"
        )
    for _, sql in triggers:
        connection.exec_driver_sql(sql)

    op.create_table(
        "conversation_automation_controls",
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("paused", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(trim(channel_id)) > 0 AND paused IN (0, 1) AND revision > 0",
            name="ck_automation_control",
        ),
    )
    op.create_table(
        "human_pause_effects",
        sa.Column(
            "event_record_id",
            sa.Integer(),
            sa.ForeignKey("operational_events.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *(
            sa.Column(name, sa.Text(), nullable=False)
            for name in (
                "provider",
                "channel_id",
                "customer_address",
                "provider_message_id",
                "applied_at",
            )
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_human_pause_revision"),
    )
    op.create_index(
        "uq_human_pause_message",
        "human_pause_effects",
        ["provider", "channel_id", "customer_address", "provider_message_id"],
        unique=True,
    )
    for action in ("INSERT", "UPDATE"):
        op.execute(f"""
            CREATE TRIGGER operational_pause_suppresses_{action.lower()}
            AFTER {action} ON conversation_automation_controls WHEN NEW.paused = 1
            BEGIN
                UPDATE message_processing SET state = 'suppressed', owner_token = NULL,
                    lease_expires_at = NULL, updated_at = NEW.updated_at
                WHERE state IN ('processing', 'retryable') AND inbound_message_id IN (
                    SELECT id FROM messages WHERE conversation_id = NEW.conversation_id
                );
            END
        """)
        op.execute(f"""
            CREATE TRIGGER operational_pause_rejects_reply_{action.lower()}
            BEFORE {action} ON messages WHEN NEW.direction = 'outbound' AND EXISTS (
                SELECT 1 FROM conversation_automation_controls
                WHERE conversation_id = NEW.conversation_id AND paused = 1
            )
            BEGIN SELECT RAISE(ABORT, 'operational pause rejects AI Reply'); END
        """)
        op.execute(f"""
            CREATE TRIGGER operational_pause_rejects_claim_{action.lower()}
            BEFORE {action} ON message_processing WHEN NEW.state = 'processing' AND EXISTS (
                SELECT 1 FROM conversation_automation_controls AS control
                JOIN messages ON messages.conversation_id = control.conversation_id
                WHERE messages.id = NEW.inbound_message_id AND control.paused = 1
            )
            BEGIN SELECT RAISE(ABORT, 'operational pause rejects generation'); END
        """)
    op.execute("""
        CREATE TRIGGER operational_pause_suppresses_admission
        AFTER INSERT ON message_processing WHEN NEW.state = 'retryable' AND EXISTS (
            SELECT 1 FROM conversation_automation_controls AS control
            JOIN messages ON messages.conversation_id = control.conversation_id
            WHERE messages.id = NEW.inbound_message_id AND control.paused = 1
        )
        BEGIN
            UPDATE message_processing SET state = 'suppressed'
            WHERE inbound_message_id = NEW.inbound_message_id;
        END
    """)


def downgrade() -> None:
    raise RuntimeError("Operational pause downgrade requires explicit backup/restore")
