"""Finite aggregate rejection observations, no payload or routing identifiers."""

from alembic import op

revision = "0023_telnyx_ingress_observations"
down_revision = "0022_telnyx_http_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE telnyx_ingress_rejections (
        reason TEXT PRIMARY KEY NOT NULL CHECK(reason='payload_rejected'),
        observations INTEGER NOT NULL CHECK(observations BETWEEN 1 AND 9223372036854775807),
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    )""")


def downgrade() -> None:
    raise RuntimeError("Downgrade requires explicitly verified backup/restore")
