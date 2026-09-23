import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic import command
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

V01_SCHEMA_WITH_DATA = """
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

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
    in_reply_to_message_id INTEGER REFERENCES messages(id),
    UNIQUE(provider, provider_message_id)
);

CREATE UNIQUE INDEX uq_messages_in_reply_to
ON messages (in_reply_to_message_id)
WHERE in_reply_to_message_id IS NOT NULL;

INSERT INTO alembic_version (version_num) VALUES ('0002_reply_idempotency');
INSERT INTO conversations (
    id, provider, customer_address, created_at, updated_at
) VALUES (
    7, 'twilio', 'whatsapp:+5511000000000',
    '2026-09-12T10:00:00+00:00', '2026-09-12T10:00:00+00:00'
);
INSERT INTO messages (
    id, conversation_id, provider, provider_message_id,
    direction, body, created_at, in_reply_to_message_id
) VALUES (
    11, 7, 'twilio', 'SM-v01-fixture', 'inbound',
    'Mensagem existente', '2026-09-12T10:00:00+00:00', NULL
);
INSERT INTO messages (
    id, conversation_id, provider, provider_message_id,
    direction, body, created_at, in_reply_to_message_id
) VALUES (
    12, 7, 'twilio', NULL, 'outbound',
    'Resposta existente', '2026-09-12T10:00:01+00:00', 11
);
"""


def _create_v0_database(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(V0_SCHEMA_WITH_DATA)


def _create_v01_database(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(V01_SCHEMA_WITH_DATA)


def _assert_migration_connection_durability(manager: MigrationManager) -> None:
    state = manager.connection_durability_state()
    assert state.journal_mode == "wal"
    assert state.synchronous == 2
    assert state.foreign_keys == 1
    assert state.busy_timeout_ms == 5_000


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

    assert {
        "alembic_version",
        "conversations",
        "messages",
        "message_processing",
        "generation_metrics",
        "outbound_deliveries",
        "delivery_attempts",
        "pending_delivery_statuses",
    }.issubset(tables)
    assert versions == [("0008_twilio_delivery_status",)]
    with sqlite3.connect(database_path) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(messages)")}
    assert "ix_messages_conversation_created" in indexes
    assert "ix_messages_conversation_direction_id" in indexes
    assert manager.is_current()
    _assert_migration_connection_durability(manager)


def test_twilio_status_inbox_migration_preserves_existing_outbox(tmp_path: Path) -> None:
    database_path = tmp_path / "status-inbox-upgrade.db"
    manager = MigrationManager(database_path)
    original_upgrade = command.upgrade

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            command,
            "upgrade",
            lambda config, _: original_upgrade(config, "0007_durable_outbox"),
        )
        manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (1, 'twilio', 'customer', '2026-09-23', '2026-09-23')
            """
        )
        connection.executemany(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                recipient_address, direction, body, created_at, in_reply_to_message_id
            ) VALUES (?, 1, 'twilio', ?, 'studio', ?, ?, '2026-09-23', ?)
            """,
            [
                (1, "SM-existing-inbound", "inbound", "inbound", None),
                (2, None, "outbound", "reply", 1),
            ],
        )
        connection.execute(
            """
            INSERT INTO outbound_deliveries (
                outbound_message_id, provider, provider_channel_id, recipient_address,
                state, attempt_count, next_attempt_at, created_at, updated_at
            ) VALUES (
                2, 'twilio', 'studio', 'customer', 'pending', 0,
                '2026-09-23', '2026-09-23', '2026-09-23'
            )
            """
        )

    manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        delivery = connection.execute(
            "SELECT outbound_message_id, state FROM outbound_deliveries"
        ).fetchall()
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(pending_delivery_statuses)")
        }
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert delivery == [(2, "pending")]
    assert {
        "provider",
        "provider_message_id",
        "status",
        "safe_error_code",
        "received_at",
        "updated_at",
    }.issubset(columns)
    assert version == "0008_twilio_delivery_status"


def test_migration_connection_really_enforces_foreign_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "migration-foreign-keys.db"
    manager = MigrationManager(database_path)
    manager.upgrade()
    original_upgrade = command.upgrade

    def inspect_migration_connection(config: Any, revision: str) -> None:
        sqlalchemy_connection = config.attributes["connection"]
        raw_connection = sqlalchemy_connection.connection.driver_connection
        assert raw_connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        with pytest.raises(sqlite3.IntegrityError):
            raw_connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at
                ) VALUES (999999, 'twilio', 'SM-orphan', 'inbound', 'body', '2026-09-22')
                """
            )
        original_upgrade(config, revision)

    monkeypatch.setattr(command, "upgrade", inspect_migration_connection)

    manager.upgrade()


def test_current_schema_requires_generation_lifecycle_triggers(tmp_path: Path) -> None:
    database_path = tmp_path / "missing-trigger.db"
    manager = MigrationManager(database_path)
    manager.upgrade()
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER create_processing_for_inbound_message")

    assert not manager.is_current()


def test_v01_database_is_upgraded_with_completed_reply_lifecycle(tmp_path: Path) -> None:
    database_path = tmp_path / "v01.db"
    _create_v01_database(database_path)

    manager = MigrationManager(database_path)
    manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        conversations = connection.execute(
            "SELECT id, provider, customer_address FROM conversations"
        ).fetchall()
        messages = connection.execute(
            """
            SELECT id, direction, body, in_reply_to_message_id, recipient_address
            FROM messages ORDER BY id
            """
        ).fetchall()
        processing = connection.execute(
            """
            SELECT inbound_message_id, state, owner_token, lease_expires_at, attempt_count
            FROM message_processing
            """
        ).fetchall()
        deliveries = connection.execute(
            """
            SELECT outbound_message_id, state, provider_message_id, safe_error_code
            FROM outbound_deliveries
            """
        ).fetchall()

    assert manager.is_current()
    assert conversations == [(7, "twilio", "whatsapp:+5511000000000")]
    assert messages == [
        (11, "inbound", "Mensagem existente", None, ""),
        (12, "outbound", "Resposta existente", 11, ""),
    ]
    assert processing == [(11, "completed", None, None, 0)]
    assert deliveries == [(12, "unknown", None, "legacy_unverified")]
    _assert_migration_connection_durability(manager)


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
            SELECT id, direction, body, in_reply_to_message_id, recipient_address
            FROM messages ORDER BY id
            """
        ).fetchall()
        deliveries = connection.execute(
            """
            SELECT outbound_message_id, state, provider_message_id, safe_error_code
            FROM outbound_deliveries
            """
        ).fetchall()

    assert manager.is_current()
    assert conversation == [(7, "twilio", "whatsapp:+5511000000000")]
    assert messages == [
        (11, "inbound", "Mensagem existente", None, ""),
        (12, "outbound", "Resposta existente", 11, ""),
    ]
    assert deliveries == [(12, "unknown", None, "legacy_unverified")]
    _assert_migration_connection_durability(manager)


def test_migration_never_queues_historical_replies_for_send(tmp_path: Path) -> None:
    database_path = tmp_path / "historical.db"
    _create_v01_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (8, 'twilio', 'whatsapp:+5511000000001', '2026-09-12', '2026-09-12')
            """
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (21, 8, 'twilio', 'SM-inbound-2', 'inbound', 'inbound', '2026-09-12', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (
                22, 8, 'twilio', 'SM-outbound-evidence',
                'outbound', 'reply', '2026-09-12', 21
            )
            """
        )

    MigrationManager(database_path).upgrade()

    with sqlite3.connect(database_path) as connection:
        states = connection.execute(
            """
            SELECT outbound_message_id, state, provider_message_id, safe_error_code
            FROM outbound_deliveries ORDER BY outbound_message_id
            """
        ).fetchall()
        pending = connection.execute(
            "SELECT COUNT(*) FROM outbound_deliveries WHERE state = 'pending'"
        ).fetchone()[0]

    assert states == [
        (12, "unknown", None, "legacy_unverified"),
        (22, "accepted_legacy", "SM-outbound-evidence", None),
    ]
    assert pending == 0


def test_migration_rejects_historical_reply_linked_across_conversations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "historical-cross-conversation.db"
    _create_v01_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (8, 'twilio', 'customer-b', '2026-09-12', '2026-09-12')
            """
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (
                21, 8, 'twilio', 'SM-cross-inbound',
                'inbound', 'inbound', '2026-09-12', NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (
                22, 7, 'twilio', NULL,
                'outbound', 'cross reply', '2026-09-12', 21
            )
            """
        )

    manager = MigrationManager(database_path)
    with pytest.raises(RuntimeError, match="valid inbound"):
        manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "outbound_deliveries" not in tables
    assert "delivery_attempts" not in tables
    assert version == "0006_conversation_context_index"


def test_failed_outbox_migration_rolls_back_new_tables_and_preserves_messages(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "failed-outbox.db"
    _create_v01_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (
                13, 7, 'twilio', NULL, 'outbound',
                'orphan historical reply', '2026-09-12T10:00:02+00:00', NULL
            )
            """
        )

    manager = MigrationManager(database_path)
    with pytest.raises(RuntimeError, match="without a valid inbound"):
        manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        messages = connection.execute("SELECT id, body FROM messages ORDER BY id").fetchall()
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "outbound_deliveries" not in tables
    assert "delivery_attempts" not in tables
    assert messages == [
        (11, "Mensagem existente"),
        (12, "Resposta existente"),
        (13, "orphan historical reply"),
    ]
    assert version == "0006_conversation_context_index"
    assert not manager.is_current()


def test_outbox_migration_rolls_back_failure_after_legacy_backfill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "failed-after-outbox-backfill.db"
    manager = MigrationManager(database_path)
    original_upgrade = command.upgrade

    with monkeypatch.context() as patch:
        patch.setattr(
            command,
            "upgrade",
            lambda config, _: original_upgrade(
                config,
                "0006_conversation_context_index",
            ),
        )
        manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (1, 'twilio', 'customer', '2026-09-12', '2026-09-12')
            """
        )
        connection.executemany(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                recipient_address, direction, body, created_at,
                in_reply_to_message_id
            ) VALUES (?, 1, 'twilio', ?, 'studio', ?, ?, '2026-09-12', ?)
            """,
            [
                (1, "SM-inbound-manual", "inbound", "manual inbound", None),
                (2, None, "outbound", "manual reply", 1),
                (3, "SM-inbound-rendered", "inbound", "rendered inbound", None),
                (4, "SM-rendered-evidence", "outbound", "rendered reply", 3),
            ],
        )
        connection.execute(
            """
            CREATE TRIGGER outbound_delivery_requires_ai_reply_insert
            BEFORE UPDATE OF body ON messages
            WHEN 0
            BEGIN
                SELECT 1;
            END
            """
        )

    with pytest.raises(SQLAlchemyError, match="already exists"):
        manager.upgrade()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        messages = connection.execute("SELECT id, body FROM messages ORDER BY id").fetchall()
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert "outbound_deliveries" not in tables
    assert "delivery_attempts" not in tables
    assert messages == [
        (1, "manual inbound"),
        (2, "manual reply"),
        (3, "rendered inbound"),
        (4, "rendered reply"),
    ]
    assert version == "0006_conversation_context_index"
    assert not manager.is_current()


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


def test_database_constraints_enforce_generation_lifecycle(tmp_path: Path) -> None:
    database_path = tmp_path / "generation-constraints.db"
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
                recipient_address, direction, body, created_at
            ) VALUES (
                1, 1, 'twilio', 'SM-inbound', 'studio',
                'inbound', 'body', '2026-09-13'
            )
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE message_processing
                SET state = 'processing', attempt_count = 1
                WHERE inbound_message_id = 1
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE message_processing
                SET state = 'unknown'
                WHERE inbound_message_id = 1
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE message_processing
                SET attempt_count = 3
                WHERE inbound_message_id = 1
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE message_processing
                SET state = 'completed'
                WHERE inbound_message_id = 1
                """
            )

        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (2, 1, 'twilio', NULL, 'outbound', 'reply', '2026-09-13', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO outbound_deliveries (
                outbound_message_id, provider, provider_channel_id, recipient_address,
                state, attempt_count, accepted_at, created_at, updated_at
            ) VALUES (
                2, 'twilio', 'studio', 'customer',
                'accepted_legacy', 0, '2026-09-13', '2026-09-13', '2026-09-13'
            )
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE message_processing
                SET state = 'suppressed'
                WHERE inbound_message_id = 1
                """
            )
        connection.execute(
            """
            UPDATE message_processing
            SET state = 'completed'
            WHERE inbound_message_id = 1
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM outbound_deliveries WHERE outbound_message_id = 2")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM messages WHERE id = 2")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE messages
                SET in_reply_to_message_id = NULL
                WHERE id = 2
                """
            )

        connection.execute(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at
            ) VALUES (3, 1, 'twilio', 'SM-suppressed', 'inbound', 'body', '2026-09-13')
            """
        )
        connection.execute(
            """
            UPDATE message_processing
            SET state = 'suppressed'
            WHERE inbound_message_id = 3
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, provider, provider_message_id,
                    direction, body, created_at, in_reply_to_message_id
                ) VALUES (1, 'twilio', NULL, 'outbound', 'reply', '2026-09-13', 3)
                """
            )
