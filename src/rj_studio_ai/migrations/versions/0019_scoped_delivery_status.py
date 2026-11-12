"""Retain scoped Telnyx status evidence without reinterpreting legacy inbox rows."""

import sqlalchemy as sa
from alembic import op

revision = "0019_scoped_delivery_status"
down_revision = "0018_inbound_event_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_deliveries",
        sa.Column("status_conflict", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "delivery_status_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        *(
            sa.Column(name, sa.Text(), nullable=False)
            for name in (
                "provider",
                "event_id",
                "provider_message_id",
                "channel_id",
                "customer_address",
                "account_id",
                "profile_id",
                "event_type",
                "recipient_status",
                "status",
                "occurred_at",
                "received_at",
            )
        ),
        # Intentionally not a cascading FK: receipts survive explicit Message purge.
        sa.Column("delivery_id", sa.Integer()),
        sa.Column("acceptance_token", sa.Text()),
        sa.UniqueConstraint("provider", "event_id", name="uq_delivery_status_event"),
        sa.CheckConstraint(
            "status IN ('unknown','sent','delivered','read','failed')",
            name="ck_delivery_status_evidence",
        ),
    )
    op.create_index(
        "ix_delivery_status_message", "delivery_status_events", ["provider", "provider_message_id"]
    )
    connection = op.get_bind()
    old = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE name='outbound_delivery_state_transition'"
    ).scalar_one()
    # Preserve all intervening handoff/pause transitions and all legacy providers.
    new = old.replace(
        "AND NOT (",
        "AND NOT ((OLD.provider = 'telnyx' AND OLD.state = 'failed' "
        "AND NEW.state IN ('delivered','read') AND NEW.status_conflict = 1 "
        "AND OLD.accepted_at IS NOT NULL) OR ",
        1,
    )
    op.execute("DROP TRIGGER outbound_delivery_state_transition")
    op.execute(new)
    op.execute("""
        CREATE TRIGGER telnyx_status_evidence_monotonic
        BEFORE UPDATE OF state, status_conflict ON outbound_deliveries
        WHEN NEW.status_conflict NOT IN (0,1)
          OR NEW.status_conflict < OLD.status_conflict
          OR (OLD.provider = 'telnyx' AND OLD.state IN ('delivered','read')
              AND NEW.state = 'failed')
        BEGIN SELECT RAISE(ABORT, 'delivery evidence cannot regress'); END
    """)
    op.execute("""
        CREATE TRIGGER delivery_conflict_rejects_submission
        BEFORE UPDATE OF state, submission_started_at ON outbound_deliveries
        WHEN ((NEW.state = 'sending' AND OLD.state != 'sending')
              OR (NEW.submission_started_at IS NOT NULL AND OLD.submission_started_at IS NULL))
          AND EXISTS (
            SELECT 1 FROM outbound_deliveries AS conflict
            JOIN messages AS prior ON prior.id=conflict.outbound_message_id
            JOIN messages AS current ON current.conversation_id=prior.conversation_id
            WHERE current.id=NEW.outbound_message_id AND conflict.status_conflict=1
          )
        BEGIN SELECT RAISE(ABORT, 'delivery conflict rejects submission'); END
    """)


def downgrade() -> None:
    raise RuntimeError("Scoped delivery evidence downgrade requires explicit backup/restore")
