"""Index bounded Conversation-context retrieval.

Revision ID: 0006_conversation_context_index
Revises: 0005_recovery_recipient_address
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_conversation_context_index"
down_revision: str | None = "0005_recovery_recipient_address"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_created", table_name="messages")
