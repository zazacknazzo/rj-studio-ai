"""Retain private keyed exact-request identity separately from purgeable deliveries."""

from alembic import op

revision = "0022_telnyx_http_identity"
down_revision = "0021_telnyx_submission_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE telnyx_http_requests (
        submission_key TEXT PRIMARY KEY NOT NULL,
        version TEXT NOT NULL CHECK(version='t11-v1'),
        integrity_key_id TEXT NOT NULL CHECK(length(integrity_key_id) BETWEEN 1 AND 64),
        request_mac TEXT NOT NULL CHECK(length(request_mac)=64)
    )""")
    for operation in ("UPDATE", "DELETE"):
        op.execute(f"""CREATE TRIGGER telnyx_http_reject_{operation.lower()}
            BEFORE {operation} ON telnyx_http_requests
            BEGIN SELECT RAISE(ABORT,'HTTP identity is immutable'); END""")
    op.execute("""CREATE TRIGGER telnyx_http_reject_replace
        BEFORE INSERT ON telnyx_http_requests WHEN EXISTS (
            SELECT 1 FROM telnyx_http_requests WHERE submission_key=NEW.submission_key)
        BEGIN SELECT RAISE(ABORT,'HTTP identity already exists'); END""")
    op.execute("""CREATE TRIGGER telnyx_http_reject_key_reuse
        BEFORE INSERT ON outbound_deliveries WHEN NEW.provider='telnyx' AND EXISTS (
            SELECT 1 FROM telnyx_http_requests WHERE submission_key=NEW.submission_key)
        BEGIN SELECT RAISE(ABORT,'HTTP identity cannot be reused'); END""")


def downgrade() -> None:
    raise RuntimeError("Downgrade requires explicitly verified backup/restore")
