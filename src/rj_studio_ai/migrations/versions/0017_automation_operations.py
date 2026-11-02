"""Opaque administrative Conversation identifiers."""

import sqlalchemy as sa
from alembic import op

revision = "0017_automation_operations"
down_revision = "0016_operational_outbound_fence"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE conversation_automation_controls ADD COLUMN resumed_at TEXT")
    op.create_table(
        "conversation_operation_ids",
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("opaque_id", sa.Text(), nullable=False, unique=True),
        sa.CheckConstraint("length(opaque_id)=32", name="ck_operation_identity"),
    )
    op.execute("""INSERT INTO conversation_operation_ids
        SELECT id, lower(hex(randomblob(16))) FROM conversations""")
    op.execute("""CREATE TRIGGER conversation_operation_identity
        AFTER INSERT ON conversations BEGIN
        INSERT INTO conversation_operation_ids VALUES (NEW.id, lower(hex(randomblob(16)))); END""")

    op.create_table(
        "automation_operation_receipts",
        sa.Column("operation_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *(
            sa.Column(name, sa.Text(), nullable=False)
            for name in ("operator_id", "action", "result_json", "created_at")
        ),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "length(operation_id)=32 AND expected_revision>=0 AND action IN ('pause','resume')",
            name="ck_operation_receipt",
        ),
    )
    op.execute("""CREATE TRIGGER automation_receipt_immutable BEFORE UPDATE
        ON automation_operation_receipts BEGIN
        SELECT RAISE(ABORT,'immutable operation receipt'); END""")

    op.execute("""CREATE TRIGGER conversation_operation_identity_immutable BEFORE UPDATE
        ON conversation_operation_ids BEGIN
        SELECT RAISE(ABORT,'immutable operation identity'); END""")
    for action in ("insert", "update"):
        op.execute(f"DROP TRIGGER operational_pause_cancels_ready_delivery_{action}")
        op.execute(f"""CREATE TRIGGER operational_pause_cancels_ready_delivery_{action}
            AFTER {action} ON outbound_deliveries
            WHEN NEW.state IN ('pending','retryable') AND EXISTS (
                SELECT 1 FROM conversation_automation_controls AS control
                JOIN messages AS outbound ON outbound.conversation_id=control.conversation_id
                JOIN message_processing AS processing
                  ON processing.inbound_message_id=outbound.in_reply_to_message_id
                WHERE outbound.id=NEW.outbound_message_id
                  AND (control.paused=1 OR processing.automation_revision != control.revision)
            ) BEGIN UPDATE outbound_deliveries SET state='cancelled', next_attempt_at=NULL,
                safe_error_code='operational_pause_cancelled' WHERE id=NEW.id; END""")


def downgrade():
    raise RuntimeError("Administrative identity downgrade requires backup/restore")
