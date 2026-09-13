import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from rj_studio_ai.domain import InboundMessage, MessageRecord


class SqliteConversationStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def record_exchange(self, message: InboundMessage, reply_body: str) -> bool:
        timestamp = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO conversations (
                    provider, customer_address, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, customer_address)
                DO UPDATE SET updated_at = excluded.updated_at
                """,
                (message.provider, message.customer_address, timestamp, timestamp),
            )
            conversation_id = connection.execute(
                """
                SELECT id FROM conversations
                WHERE provider = ? AND customer_address = ?
                """,
                (message.provider, message.customer_address),
            ).fetchone()[0]

            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at
                ) VALUES (?, ?, ?, 'inbound', ?, ?)
                """,
                (
                    conversation_id,
                    message.provider,
                    message.provider_message_id,
                    message.body,
                    timestamp,
                ),
            ).rowcount
            if not inserted:
                return False

            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at
                ) VALUES (?, ?, NULL, 'outbound', ?, ?)
                """,
                (conversation_id, message.provider, reply_body, timestamp),
            )
        return True

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

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY,
                    provider TEXT NOT NULL,
                    customer_address TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider, customer_address)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    provider_message_id TEXT,
                    direction TEXT NOT NULL
                        CHECK(direction IN ('inbound', 'outbound')),
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(provider, provider_message_id)
                );
                """
            )
