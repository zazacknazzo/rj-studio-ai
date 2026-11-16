"""Durable Telnyx channel gate; no activation authority or destructive table rebuild."""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0020_channel_lifecycle"
down_revision = "0019_scoped_delivery_status"
branch_labels = None
depends_on = None


def _blocked(provider: str, channel: str) -> str:
    # All arguments are fixed SQL expressions, never external values.
    return f"""({provider}='telnyx' AND NOT EXISTS (
        SELECT 1 FROM eligible_telnyx_channels WHERE channel_id={channel}))"""


def _cancel(timestamp: str) -> str:
    eligible = f"""SELECT id FROM outbound_deliveries WHERE
        {_blocked("provider", "provider_channel_id")}
        AND (state IN ('pending','retryable')
             OR (state='sending' AND submission_started_at IS NULL))"""
    return f"""
        UPDATE delivery_attempts SET outcome='failed',safe_error_code='channel_lifecycle_cancelled',
            completed_at={timestamp} WHERE outcome='started'
            AND outbound_delivery_id IN ({eligible});
        UPDATE outbound_deliveries SET state='cancelled',owner_token=NULL,lease_expires_at=NULL,
            next_attempt_at=NULL,safe_error_code='channel_lifecycle_cancelled',updated_at={timestamp}
            WHERE id IN ({eligible});
        UPDATE message_processing SET state='suppressed',owner_token=NULL,lease_expires_at=NULL,
            updated_at={timestamp} WHERE state IN ('processing','retryable') AND inbound_message_id
            IN (SELECT id FROM messages WHERE direction='inbound' AND
                {_blocked("provider", "recipient_address")});
    """


def upgrade() -> None:
    op.create_table(
        "channel_lifecycle",
        sa.Column("provider", sa.Text(), primary_key=True),
        *(
            sa.Column(n, sa.Text(), nullable=False)
            for n in (
                "waba_id",
                "channel_id",
                "organization_id",
                "profile_id",
                "state",
                "updated_at",
            )
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("verification_evidence", sa.Text()),
        sa.Column(
            "last_event_record_id",
            sa.Integer(),
            sa.ForeignKey("operational_events.id", ondelete="RESTRICT"),
        ),
        sa.CheckConstraint(
            "provider='telnyx' AND revision>=0 AND length(waba_id)>0 AND length(channel_id)>0 "
            "AND length(organization_id)>0 AND length(profile_id)>0 "
            "AND state IN ('active','blocked','verification_required') "
            "AND (state!='active' OR (verification_evidence IS NOT NULL "
            "AND length(trim(verification_evidence))>0 AND last_event_record_id IS NULL))",
            name="ck_channel_lifecycle",
        ),
    )
    op.create_table(
        "channel_lifecycle_effects",
        sa.Column(
            "event_record_id",
            sa.Integer(),
            sa.ForeignKey("operational_events.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.execute("""CREATE VIEW eligible_telnyx_channels AS
        SELECT channel_id FROM channel_lifecycle WHERE provider='telnyx' AND state='active'
        AND verification_evidence IS NOT NULL AND last_event_record_id IS NULL""")
    op.execute("""CREATE TRIGGER channel_binding_immutable BEFORE UPDATE ON channel_lifecycle
        WHEN NEW.provider IS NOT OLD.provider OR NEW.waba_id IS NOT OLD.waba_id
          OR NEW.channel_id IS NOT OLD.channel_id OR NEW.organization_id IS NOT OLD.organization_id
          OR NEW.profile_id IS NOT OLD.profile_id OR NEW.revision<OLD.revision
          OR (OLD.state!='active' AND NEW.state='active')
        BEGIN SELECT RAISE(ABORT,'channel binding or activation requires authorization'); END""")
    for table in ("channel_lifecycle", "channel_lifecycle_effects"):
        op.execute(f"""CREATE TRIGGER {table}_retained BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT,'channel lifecycle evidence retained'); END""")
    op.execute("""CREATE TRIGGER channel_effect_immutable BEFORE UPDATE ON channel_lifecycle_effects
        BEGIN SELECT RAISE(ABORT,'channel effect is immutable'); END""")
    connection = op.get_bind()
    old = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master "
        "WHERE name='delivery_attempt_finalization_requires_current_claim'"
    ).scalar_one()
    op.execute("DROP TRIGGER delivery_attempt_finalization_requires_current_claim")
    op.execute(
        old.replace(
            "'operational_pause_cancelled'",
            "'operational_pause_cancelled', 'channel_lifecycle_cancelled'",
        )
    )
    for action in ("INSERT", "UPDATE"):
        op.execute(f"""CREATE TRIGGER channel_lifecycle_fences_{action.lower()}
            AFTER {action} ON channel_lifecycle WHEN NEW.state!='active'
            BEGIN {_cancel("NEW.updated_at")} END""")
        op.execute(f"""CREATE TRIGGER channel_rejects_generation_{action.lower()}
            BEFORE {action} ON message_processing WHEN NEW.state='processing' AND EXISTS (
                SELECT 1 FROM messages WHERE id=NEW.inbound_message_id AND
                {_blocked("provider", "recipient_address")})
            BEGIN SELECT RAISE(ABORT,'channel rejects generation'); END""")
        op.execute(f"""CREATE TRIGGER channel_rejects_reply_{action.lower()}
            BEFORE {action} ON messages WHEN NEW.direction='outbound' AND EXISTS (
                SELECT 1 FROM messages AS inbound WHERE inbound.id=NEW.in_reply_to_message_id AND
                {_blocked("inbound.provider", "inbound.recipient_address")})
            BEGIN SELECT RAISE(ABORT,'channel rejects reply'); END""")
        op.execute(f"""CREATE TRIGGER channel_cancels_ready_delivery_{action.lower()}
            AFTER {action} ON outbound_deliveries WHEN NEW.state IN ('pending','retryable') AND
                {_blocked("NEW.provider", "NEW.provider_channel_id")}
            BEGIN UPDATE outbound_deliveries SET state='cancelled',next_attempt_at=NULL,
                safe_error_code='channel_lifecycle_cancelled' WHERE id=NEW.id; END""")
    op.execute(f"""CREATE TRIGGER channel_suppresses_admission AFTER INSERT ON message_processing
        WHEN NEW.state='retryable' AND EXISTS (
            SELECT 1 FROM messages WHERE id=NEW.inbound_message_id
            AND {_blocked("provider", "recipient_address")})
        BEGIN UPDATE message_processing SET state='suppressed'
            WHERE inbound_message_id=NEW.inbound_message_id; END""")
    op.execute(f"""CREATE TRIGGER channel_rejects_submission
        BEFORE UPDATE OF state,submission_started_at ON outbound_deliveries
        WHEN ((NEW.state='sending' AND OLD.state!='sending') OR
            (NEW.submission_started_at IS NOT NULL AND OLD.submission_started_at IS NULL))
            AND {_blocked("NEW.provider", "NEW.provider_channel_id")}
        BEGIN SELECT RAISE(ABORT,'channel rejects submission'); END""")
    # Unverified historical Telnyx work cannot become newly sendable on upgrade.
    timestamp = datetime.now(UTC).isoformat()
    for statement in _cancel(":timestamp").split(";"):
        if statement.strip():
            connection.exec_driver_sql(statement, {"timestamp": timestamp})


def downgrade() -> None:
    raise RuntimeError("Channel lifecycle downgrade requires explicit backup/restore")
