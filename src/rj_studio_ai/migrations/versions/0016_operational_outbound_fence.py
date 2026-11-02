"""Cancel only proven-unsubmitted work when operational pause takes effect."""

from datetime import UTC, datetime

from alembic import op

revision = "0016_operational_outbound_fence"
down_revision = "0015_operational_generation_pause"
branch_labels = None
depends_on = None


def _cancellation_statements(conversation: str, timestamp: str) -> tuple[str, str]:
    # Arguments are fixed SQL expressions, never payload values. Keep the attempt
    # finalization before owner invalidation so existing ownership guards hold.
    eligible = f"""
        SELECT delivery.id FROM outbound_deliveries AS delivery
        JOIN messages ON messages.id = delivery.outbound_message_id
        WHERE messages.conversation_id = {conversation}
          AND (delivery.state IN ('pending', 'retryable')
               OR (delivery.state = 'sending' AND delivery.submission_started_at IS NULL))
    """
    return (
        f"""UPDATE delivery_attempts SET outcome = 'failed',
            safe_error_code = 'operational_pause_cancelled', completed_at = {timestamp}
            WHERE outcome = 'started' AND outbound_delivery_id IN ({eligible})""",
        f"""UPDATE outbound_deliveries SET state = 'cancelled', owner_token = NULL,
            lease_expires_at = NULL, next_attempt_at = NULL,
            safe_error_code = 'operational_pause_cancelled', updated_at = {timestamp}
            WHERE id IN ({eligible})""",
    )


def upgrade() -> None:
    op.execute("DROP TRIGGER delivery_attempt_finalization_requires_current_claim")
    op.execute("""
        CREATE TRIGGER delivery_attempt_finalization_requires_current_claim
        BEFORE UPDATE OF outcome, provider_message_id, safe_error_code, completed_at
        ON delivery_attempts
        WHEN OLD.outcome = 'started' AND NEW.outcome != 'started' AND NOT EXISTS (
            SELECT 1 FROM outbound_deliveries AS delivery
            WHERE delivery.id = OLD.outbound_delivery_id AND delivery.state = 'sending'
              AND delivery.owner_token = OLD.owner_token
              AND delivery.attempt_count = OLD.attempt_number
              AND (
                delivery.lease_expires_at > NEW.completed_at
                OR (NEW.outcome = 'unknown' AND NEW.safe_error_code = 'sending_lease_expired'
                    AND delivery.lease_expires_at <= NEW.completed_at)
                OR (NEW.outcome = 'failed'
                    AND NEW.safe_error_code IN (
                        'handoff_cancelled_before_submission', 'operational_pause_cancelled'
                    ) AND delivery.submission_started_at IS NULL)
              )
        )
        BEGIN SELECT RAISE(ABORT, 'Delivery Attempt finalization requires current claim'); END
    """)
    for action in ("INSERT", "UPDATE"):
        statements = ";\n".join(_cancellation_statements("NEW.conversation_id", "NEW.updated_at"))
        op.execute(f"""
            CREATE TRIGGER operational_pause_cancels_outbound_{action.lower()}
            AFTER {action} ON conversation_automation_controls WHEN NEW.paused = 1
            BEGIN {statements}; END
        """)
        # A late proven-retryable result remains evidence on its completed attempt,
        # but can never reschedule work in the paused Conversation.
        op.execute(f"""
            CREATE TRIGGER operational_pause_cancels_ready_delivery_{action.lower()}
            AFTER {action} ON outbound_deliveries
            WHEN NEW.state IN ('pending', 'retryable') AND EXISTS (
                SELECT 1 FROM conversation_automation_controls AS control
                JOIN messages ON messages.conversation_id = control.conversation_id
                WHERE messages.id = NEW.outbound_message_id AND control.paused = 1
            )
            BEGIN
                UPDATE outbound_deliveries SET state = 'cancelled', next_attempt_at = NULL,
                    safe_error_code = 'operational_pause_cancelled'
                WHERE id = NEW.id;
            END
        """)
    op.execute("""
        CREATE TRIGGER operational_pause_rejects_delivery_authorization
        BEFORE UPDATE OF state, submission_started_at ON outbound_deliveries
        WHEN ((NEW.state = 'sending' AND OLD.state != 'sending')
              OR (NEW.submission_started_at IS NOT NULL AND OLD.submission_started_at IS NULL))
          AND EXISTS (
              SELECT 1 FROM conversation_automation_controls AS control
              JOIN messages ON messages.conversation_id = control.conversation_id
              WHERE messages.id = NEW.outbound_message_id AND control.paused = 1
          )
        BEGIN SELECT RAISE(ABORT, 'operational pause rejects outbound authorization'); END
    """)
    # Existing Ticket 03 pauses already have effect receipts: no replay or revision
    # bump is required to protect their outboxes at this upgrade boundary.
    connection = op.get_bind()
    timestamp = datetime.now(UTC).isoformat()
    for (conversation_id,) in connection.exec_driver_sql(
        "SELECT conversation_id FROM conversation_automation_controls WHERE paused = 1"
    ).fetchall():
        for statement in _cancellation_statements(":conversation", ":timestamp"):
            connection.exec_driver_sql(
                statement, {"conversation": conversation_id, "timestamp": timestamp}
            )


def downgrade() -> None:
    raise RuntimeError("Outbound pause downgrade requires explicit backup/restore")
