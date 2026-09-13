import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rj_studio_ai.domain import InboundMessage, MessageRecord
from rj_studio_ai.migrations import MigrationManager


class PersistenceUnavailable(RuntimeError):
    """Raised when SQLite cannot complete a persistence operation."""


@dataclass(frozen=True, slots=True)
class PurgeResult:
    messages_deleted: int
    conversations_deleted: int


@dataclass(frozen=True, slots=True)
class ConversationDeletionResult:
    messages_deleted: int
    conversations_deleted: int


class SqliteConversationStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._migrations = MigrationManager(database_path)

    def initialize(self) -> None:
        self._migrations.upgrade()

    def migrations_are_current(self) -> bool:
        return self._migrations.is_current()

    def is_writable(self) -> bool:
        if not self._database_path.is_file():
            return False
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE alembic_version SET version_num = version_num")
                connection.rollback()
        except sqlite3.Error:
            return False
        return True

    def get_or_create_reply(self, message: InboundMessage, reply_body: str) -> str:
        try:
            return self._get_or_create_reply(message, reply_body)
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error

    def purge_messages_older_than(self, cutoff: datetime) -> PurgeResult:
        if cutoff.utcoffset() is None:
            raise ValueError("Retention cutoff must include a timezone")
        cutoff_text = cutoff.astimezone(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                messages_deleted = connection.execute(
                    "DELETE FROM messages WHERE created_at < ?",
                    (cutoff_text,),
                ).rowcount
                conversations_deleted = connection.execute(
                    """
                    DELETE FROM conversations
                    WHERE NOT EXISTS (
                        SELECT 1 FROM messages
                        WHERE messages.conversation_id = conversations.id
                    )
                    """
                ).rowcount
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error
        return PurgeResult(
            messages_deleted=messages_deleted,
            conversations_deleted=conversations_deleted,
        )

    def delete_conversation(
        self,
        *,
        provider: str,
        customer_address: str,
    ) -> ConversationDeletionResult:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT id FROM conversations
                    WHERE provider = ? AND customer_address = ?
                    """,
                    (provider, customer_address),
                ).fetchone()
                if row is None:
                    return ConversationDeletionResult(0, 0)
                conversation_id = int(row[0])
                messages_deleted = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                        (conversation_id,),
                    ).fetchone()[0]
                )
                conversations_deleted = connection.execute(
                    "DELETE FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).rowcount
        except sqlite3.Error as error:
            raise PersistenceUnavailable("Conversation persistence is unavailable") from error
        return ConversationDeletionResult(
            messages_deleted=messages_deleted,
            conversations_deleted=conversations_deleted,
        )

    def _get_or_create_reply(self, message: InboundMessage, reply_body: str) -> str:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT inbound.id, inbound.conversation_id, outbound.body
                FROM messages AS inbound
                LEFT JOIN messages AS outbound
                  ON outbound.in_reply_to_message_id = inbound.id
                WHERE inbound.provider = ?
                  AND inbound.provider_message_id = ?
                  AND inbound.direction = 'inbound'
                """,
                (message.provider, message.provider_message_id),
            ).fetchone()
            if existing is not None and existing[2] is not None:
                return str(existing[2])

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO conversations (
                        provider, customer_address, created_at, updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider, customer_address)
                    DO NOTHING
                    """,
                    (message.provider, message.customer_address, timestamp, timestamp),
                )
                conversation_id = int(
                    connection.execute(
                        """
                        SELECT id FROM conversations
                        WHERE provider = ? AND customer_address = ?
                        """,
                        (message.provider, message.customer_address),
                    ).fetchone()[0]
                )
                inbound_message_id = int(
                    connection.execute(
                        """
                        INSERT INTO messages (
                            conversation_id, provider, provider_message_id,
                            direction, body, created_at
                        ) VALUES (?, ?, ?, 'inbound', ?, ?)
                        RETURNING id
                        """,
                        (
                            conversation_id,
                            message.provider,
                            message.provider_message_id,
                            message.body,
                            timestamp,
                        ),
                    ).fetchone()[0]
                )
            else:
                inbound_message_id = int(existing[0])
                conversation_id = int(existing[1])

            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (?, ?, NULL, 'outbound', ?, ?, ?)
                """,
                (
                    conversation_id,
                    message.provider,
                    reply_body,
                    timestamp,
                    inbound_message_id,
                ),
            )
            connection.execute(
                """
                UPDATE conversations SET updated_at = ? WHERE id = ?
                """,
                (timestamp, conversation_id),
            )
        return reply_body

    def get_history(
        self,
        *,
        provider: str,
        customer_address: str,
    ) -> list[MessageRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT messages.direction, messages.body
                FROM messages
                JOIN conversations ON conversations.id = messages.conversation_id
                WHERE conversations.provider = ?
                  AND conversations.customer_address = ?
                ORDER BY messages.id
                """,
                (provider, customer_address),
            ).fetchall()
        return [MessageRecord(direction=row[0], body=row[1]) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
