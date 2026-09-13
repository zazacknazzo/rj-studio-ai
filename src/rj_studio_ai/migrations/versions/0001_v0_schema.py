"""Create the V0 Conversation and Message schema.

Revision ID: 0001_v0_schema
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_v0_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    v0_tables = {"conversations", "messages"}

    if existing.isdisjoint(v0_tables):
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("customer_address", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint(
                "provider",
                "customer_address",
                name="uq_conversations_provider_customer",
            ),
        )
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("provider_message_id", sa.Text()),
            sa.Column("direction", sa.Text(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.CheckConstraint(
                "direction IN ('inbound', 'outbound')",
                name="ck_messages_direction",
            ),
            sa.UniqueConstraint(
                "provider",
                "provider_message_id",
                name="uq_messages_provider_message",
            ),
        )
        return

    if not v0_tables.issubset(existing):
        raise RuntimeError("Partial V0 schema cannot be migrated safely")

    required_columns = {
        "conversations": {"id", "provider", "customer_address", "created_at", "updated_at"},
        "messages": {
            "id",
            "conversation_id",
            "provider",
            "provider_message_id",
            "direction",
            "body",
            "created_at",
        },
    }
    inspector = sa.inspect(op.get_bind())
    for table, required in required_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table)}
        if not required.issubset(actual):
            raise RuntimeError(f"Existing {table} table does not match the V0 schema")


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
