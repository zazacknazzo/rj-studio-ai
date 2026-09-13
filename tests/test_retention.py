import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app
from rj_studio_ai.maintenance import main as maintenance_main
from rj_studio_ai.persistence import SqliteConversationStore


def _insert_retention_fixture(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            """
            INSERT INTO conversations (
                id, provider, customer_address, created_at, updated_at
            ) VALUES (?, 'twilio', ?, ?, ?)
            """,
            [
                (1, "customer-expired", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
                (2, "customer-active", "2026-01-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00"),
                (3, "customer-cutoff", "2026-06-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO messages (
                id, conversation_id, provider, provider_message_id,
                direction, body, created_at, in_reply_to_message_id
            ) VALUES (?, ?, 'twilio', ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "SM-expired", "inbound", "old inbound", "2026-01-01T00:00:00+00:00", None),
                (2, 1, None, "outbound", "old reply", "2026-01-01T00:00:00+00:00", 1),
                (
                    3,
                    2,
                    "SM-active-old",
                    "inbound",
                    "old active inbound",
                    "2026-01-01T00:00:00+00:00",
                    None,
                ),
                (4, 2, None, "outbound", "old active reply", "2026-01-01T00:00:00+00:00", 3),
                (
                    5,
                    2,
                    "SM-active-new",
                    "inbound",
                    "new inbound",
                    "2026-08-01T00:00:00+00:00",
                    None,
                ),
                (6, 2, None, "outbound", "new reply", "2026-08-01T00:00:00+00:00", 5),
                (7, 3, "SM-cutoff", "inbound", "cutoff inbound", "2026-06-01T00:00:00+00:00", None),
                (8, 3, None, "outbound", "cutoff reply", "2026-06-01T00:00:00+00:00", 7),
            ],
        )


def test_explicit_purge_removes_only_messages_older_than_cutoff(tmp_path: Path) -> None:
    database_path = tmp_path / "conversations.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    _insert_retention_fixture(database_path)
    cutoff = datetime(2026, 6, 1, tzinfo=UTC)

    first = store.purge_messages_older_than(cutoff)
    second = store.purge_messages_older_than(cutoff)

    with sqlite3.connect(database_path) as connection:
        remaining_message_ids = [
            row[0] for row in connection.execute("SELECT id FROM messages ORDER BY id")
        ]
        remaining_conversation_ids = [
            row[0] for row in connection.execute("SELECT id FROM conversations ORDER BY id")
        ]

    assert (first.messages_deleted, first.conversations_deleted) == (4, 1)
    assert (second.messages_deleted, second.conversations_deleted) == (0, 0)
    assert remaining_message_ids == [5, 6, 7, 8]
    assert remaining_conversation_ids == [2, 3]


def test_explicit_conversation_deletion_removes_only_selected_customer(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "conversations.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    _insert_retention_fixture(database_path)

    first = store.delete_conversation(
        provider="twilio",
        customer_address="customer-active",
    )
    second = store.delete_conversation(
        provider="twilio",
        customer_address="customer-active",
    )

    with sqlite3.connect(database_path) as connection:
        remaining_customers = [
            row[0]
            for row in connection.execute("SELECT customer_address FROM conversations ORDER BY id")
        ]

    assert (first.messages_deleted, first.conversations_deleted) == (4, 1)
    assert (second.messages_deleted, second.conversations_deleted) == (0, 0)
    assert remaining_customers == ["customer-expired", "customer-cutoff"]


def test_expired_messages_are_not_deleted_during_application_startup(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "conversations.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    _insert_retention_fixture(database_path)
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    with sqlite3.connect(database_path) as connection:
        message_count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    assert message_count == 8


def test_maintenance_purge_uses_retention_policy_and_reports_only_counts(
    tmp_path: Path,
    capsys,
) -> None:
    database_path = tmp_path / "conversations.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    _insert_retention_fixture(database_path)

    exit_code = maintenance_main(
        [
            "--database-path",
            str(database_path),
            "purge-messages",
            "--retention-days",
            "90",
        ],
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output == "Deleted messages=4 conversations=1.\n"
    assert "customer-" not in output
