"""Link each prepared outbound reply to its inbound Message.

Revision ID: 0002_reply_idempotency
Revises: 0001_v0_schema
"""

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_reply_idempotency"
down_revision: str | None = "0001_v0_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE messages
        ADD COLUMN in_reply_to_message_id INTEGER REFERENCES messages(id)
        """
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, conversation_id, direction
            FROM messages
            ORDER BY conversation_id, id
            """
        )
    )
    pending: dict[int, list[int]] = defaultdict(list)
    for message_id, conversation_id, direction in rows:
        if direction == "inbound":
            pending[conversation_id].append(message_id)
        elif pending[conversation_id]:
            inbound_id = pending[conversation_id].pop()
            connection.execute(
                sa.text(
                    """
                    UPDATE messages
                    SET in_reply_to_message_id = :inbound_id
                    WHERE id = :outbound_id
                    """
                ),
                {"inbound_id": inbound_id, "outbound_id": message_id},
            )

    op.create_index(
        "uq_messages_in_reply_to",
        "messages",
        ["in_reply_to_message_id"],
        unique=True,
        sqlite_where=sa.text("in_reply_to_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_in_reply_to", table_name="messages")
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("in_reply_to_message_id")
