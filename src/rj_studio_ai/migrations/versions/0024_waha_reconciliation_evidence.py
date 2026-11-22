"""Allow proven WAHA acceptance reconciliation without weakening other providers."""

from alembic import op

revision = "0024_waha_reconciliation"
down_revision = "0023_telnyx_ingress_observations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE waha_reconciliation_evidence (
        delivery_id INTEGER PRIMARY KEY NOT NULL,
        intent_id TEXT NOT NULL UNIQUE CHECK(length(intent_id)=64),
        provider_message_id TEXT NOT NULL UNIQUE,
        request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
        authority_revision INTEGER NOT NULL CHECK(authority_revision>0),
        evidence_digest TEXT NOT NULL CHECK(length(evidence_digest)=64),
        observed_at TEXT NOT NULL
    )""")
    op.execute("""CREATE TRIGGER waha_reconciliation_requires_submission
        BEFORE INSERT ON waha_reconciliation_evidence WHEN NOT EXISTS (
            SELECT 1 FROM outbound_deliveries d WHERE d.id=NEW.delivery_id
            AND d.provider='waha' AND d.state IN ('unknown','sending')
            AND d.first_submission_at IS NOT NULL AND d.submission_started_at IS NOT NULL
            AND d.payload_fingerprint=NEW.request_digest AND d.attempt_count>0
        ) BEGIN SELECT RAISE(ABORT,'WAHA reconciliation requires a potential submission'); END
    """)
    op.execute("""CREATE TRIGGER waha_reconciliation_evidence_immutable
        BEFORE UPDATE ON waha_reconciliation_evidence
        BEGIN SELECT RAISE(ABORT,'WAHA reconciliation evidence is immutable'); END
    """)
    op.execute("""CREATE TRIGGER waha_reconciliation_evidence_no_delete
        BEFORE DELETE ON waha_reconciliation_evidence
        BEGIN SELECT RAISE(ABORT,'WAHA reconciliation evidence is immutable'); END
    """)
    delivery_proof = """OLD.provider='waha' AND OLD.state='unknown' AND NEW.state='accepted'
        AND EXISTS (SELECT 1 FROM waha_reconciliation_evidence e
            WHERE e.delivery_id=OLD.id AND e.provider_message_id=NEW.provider_message_id
            AND e.request_digest=OLD.payload_fingerprint)"""
    attempt_proof = """OLD.outcome IN ('unknown','started') AND NEW.outcome='accepted'
        AND EXISTS (SELECT 1 FROM waha_reconciliation_evidence e
            JOIN outbound_deliveries d ON d.id=e.delivery_id
            WHERE e.delivery_id=OLD.outbound_delivery_id AND d.provider='waha'
            AND d.first_submission_at IS NOT NULL AND d.payload_fingerprint=e.request_digest
            AND e.provider_message_id=NEW.provider_message_id
            AND d.attempt_count=OLD.attempt_number)"""
    for name, proof in (
        ("outbound_delivery_state_transition", delivery_proof),
        ("delivery_attempt_finalization_requires_current_claim", attempt_proof),
        ("terminal_delivery_attempt_is_immutable", attempt_proof),
    ):
        old = (
            op.get_bind()
            .exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
            )
            .scalar_one()
        )
        if "WHEN " not in old:
            raise RuntimeError("Expected canonical trigger missing")
        op.execute("DROP TRIGGER " + name)
        op.execute(old.replace("WHEN ", "WHEN NOT (" + proof + ") AND ", 1))


def downgrade():
    raise RuntimeError("Reconciliation evidence requires explicit verified backup/restore")
