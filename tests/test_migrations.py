import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from rj_studio_ai.migrations import MigrationManager

V0_SCHEMA_WITH_DATA = """
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    customer_address TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, customer_address)
);

CREATE TABLE messages (
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

INSERT INTO conversations (
    id, provider, customer_address, created_at, updated_at
) VALUES (
    7, 'twilio', 'whatsapp:+5511000000000',
    '2026-09-12T10:00:00+00:00', '2026-09-12T10:00:00+00:00'
);
INSERT INTO messages (
    id, conversation_id, provider, provider_message_id,
    direction, body, created_at
) VALUES (
    11, 7, 'twilio', 'SM-v0-fixture', 'inbound',
    'Mensagem existente', '2026-09-12T10:00:00+00:00'
);
INSERT INTO messages (
    id, conversation_id, provider, provider_message_id,
    direction, body, created_at
) VALUES (
    12, 7, 'twilio', NULL, 'outbound',
    'Resposta existente', '2026-09-12T10:00:00+00:00'
);
"""


def _create_v0_database(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(V0_SCHEMA_WITH_DATA)


def test_fresh_database_is_migrated_and_upgrade_is_repeatable(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.db"
    manager = MigrationManager(database_path)

    manager.upgrade()
    manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        versions = connection.execute("SELECT version_num FROM alembic_version").fetchall()

    assert {"alembic_version", "conversations", "messages"}.issubset(tables)
    assert versions == [("0002_reply_idempotency",)]
    assert manager.is_current()


def test_v0_database_is_upgraded_without_losing_messages(tmp_path: Path) -> None:
    database_path = tmp_path / "v0.db"
    _create_v0_database(database_path)

    manager = MigrationManager(database_path)
    manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        conversation = connection.execute(
            "SELECT id, provider, customer_address FROM conversations"
        ).fetchall()
        messages = connection.execute(
            """
            SELECT id, direction, body, in_reply_to_message_id
            FROM messages ORDER BY id
            """
        ).fetchall()

    assert manager.is_current()
    assert conversation == [(7, "twilio", "whatsapp:+5511000000000")]
    assert messages == [
        (11, "inbound", "Mensagem existente", None),
        (12, "outbound", "Resposta existente", 11),
    ]


def test_failed_legacy_schema_migration_is_not_marked_current(tmp_path: Path) -> None:
    database_path = tmp_path / "partial.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY)")

    manager = MigrationManager(database_path)

    with pytest.raises(RuntimeError, match="Partial V0 schema"):
        manager.upgrade()

    assert not manager.is_current()


def test_failed_migration_rolls_back_schema_and_preserves_v0_data(tmp_path: Path) -> None:
    database_path = tmp_path / "failed-after-mutation.db"
    _create_v0_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TRIGGER fail_reply_backfill
            BEFORE UPDATE OF in_reply_to_message_id ON messages
            BEGIN
                SELECT RAISE(ABORT, 'synthetic migration failure');
            END;
            """
        )

    manager = MigrationManager(database_path)
    with pytest.raises(SQLAlchemyError, match="synthetic migration failure"):
        manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        message_columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
        messages = connection.execute("SELECT id, body FROM messages ORDER BY id").fetchall()
        versions = connection.execute("SELECT version_num FROM alembic_version").fetchall()

    assert "in_reply_to_message_id" not in message_columns
    assert messages == [(11, "Mensagem existente"), (12, "Resposta existente")]
    assert versions == [("0001_v0_schema",)]
    assert not manager.is_current()


def test_database_constraints_prevent_a_second_reply_for_one_inbound_message(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "constrained.db"
    MigrationManager(database_path).upgrade()
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (1, 'twilio', 'customer', '2026-09-13', '2026-09-13')
            """
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at
            ) VALUES (
                1, 1, 'twilio', 'SM-unique', 'inbound', 'inbound', '2026-09-13'
            )
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at
                ) VALUES (
                    1, 'twilio', 'SM-unique', 'inbound', 'duplicate', '2026-09-13'
                )
                """
            )
        connection.execute(
            """
            INSERT INTO messages (
                conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (1, 'twilio', NULL, 'outbound', 'first', '2026-09-13', 1)
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (1, 'twilio', NULL, 'outbound', 'second', '2026-09-13', 1)
                """
            )
