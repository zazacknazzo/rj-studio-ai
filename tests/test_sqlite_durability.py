import sqlite3
from pathlib import Path
from time import monotonic

import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.config import Settings
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.main import create_app
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.sqlite import (
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    SqliteDurabilityError,
    apply_sqlite_connection_pragmas,
    configure_sqlite_connection,
    inspect_sqlite_connection,
)


def _message(provider_message_id: str = "SM-durable") -> InboundMessage:
    return InboundMessage(
        provider="twilio",
        provider_message_id=provider_message_id,
        customer_address="whatsapp:+5511999999999",
        recipient_address="whatsapp:+14155238886",
        body="Olá",
    )


def test_new_file_database_uses_verified_durability_pragmas(tmp_path: Path) -> None:
    database_path = tmp_path / "new.db"
    store = SqliteConversationStore(database_path)

    store.initialize()

    assert store.sqlite_durability_checks() == {
        "sqlite_storage": "ok",
        "sqlite_journal_mode": "ok",
        "sqlite_synchronous": "ok",
        "sqlite_foreign_keys": "ok",
        "sqlite_busy_timeout": "ok",
    }
    with sqlite3.connect(database_path) as reopened:
        assert reopened.execute("PRAGMA journal_mode").fetchone() == ("wal",)


def test_reopened_database_keeps_wal_and_runtime_connection_settings(tmp_path: Path) -> None:
    database_path = tmp_path / "reopened.db"
    SqliteConversationStore(database_path).initialize()

    restarted_store = SqliteConversationStore(database_path)
    assert set(restarted_store.sqlite_durability_checks().values()) == {"ok"}


def test_runtime_connection_enforces_foreign_keys_on_every_new_connection(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "foreign-keys.db"
    MigrationManager(database_path).upgrade()

    for provider_message_id in ("SM-orphan", "SM-orphan-2"):
        with sqlite3.connect(database_path) as connection:
            configure_sqlite_connection(
                connection,
                busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
                set_journal_mode=False,
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, provider, provider_message_id,
                        direction, body, created_at
                    ) VALUES (999999, 'twilio', ?, 'inbound', 'orphan', '2026-09-22')
                    """,
                    (provider_message_id,),
                )


def test_migration_connections_use_the_same_required_pragmas(tmp_path: Path) -> None:
    manager = MigrationManager(tmp_path / "migration.db")
    manager.upgrade()

    state = manager.connection_durability_state()

    assert state.journal_mode == "wal"
    assert state.synchronous == 2
    assert state.foreign_keys == 1
    assert state.busy_timeout_ms == 5_000


def test_busy_timeout_matches_connect_timeout_policy(tmp_path: Path) -> None:
    database_path = tmp_path / "busy.db"
    store = SqliteConversationStore(database_path)
    store.initialize()

    assert store.connection_durability_state().busy_timeout_ms == int(
        DEFAULT_BUSY_TIMEOUT_SECONDS * 1_000
    )
    assert MigrationManager(database_path).connection_durability_state().busy_timeout_ms == int(
        DEFAULT_BUSY_TIMEOUT_SECONDS * 1_000
    )


def test_invalid_busy_timeout_fails_closed() -> None:
    with (
        sqlite3.connect(":memory:") as connection,
        pytest.raises(SqliteDurabilityError, match="busy timeout"),
    ):
        configure_sqlite_connection(
            connection,
            busy_timeout_seconds=-1,
            set_journal_mode=False,
        )


@pytest.mark.parametrize("invalid_timeout", [0.0001, float("inf"), float("nan")])
def test_non_effective_busy_timeout_fails_closed(invalid_timeout: float) -> None:
    with (
        sqlite3.connect(":memory:") as connection,
        pytest.raises(SqliteDurabilityError, match="busy timeout"),
    ):
        configure_sqlite_connection(
            connection,
            busy_timeout_seconds=invalid_timeout,
            set_journal_mode=False,
        )


def test_wal_requirement_cannot_be_silently_ignored() -> None:
    with (
        sqlite3.connect(":memory:") as connection,
        pytest.raises(SqliteDurabilityError, match="WAL"),
    ):
        configure_sqlite_connection(
            connection,
            busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
            set_journal_mode=True,
        )


def test_memory_database_is_rejected_as_non_durable() -> None:
    store = SqliteConversationStore(Path(":memory:"))

    with pytest.raises(SqliteDurabilityError, match="file-backed"):
        store.initialize()

    assert store.sqlite_durability_checks()["sqlite_storage"] == "failed"


def test_application_startup_rejects_memory_database() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=Path(":memory:"),
            twilio_validate_signature=False,
        )
    )

    with pytest.raises(SqliteDurabilityError, match="file-backed"), TestClient(app):
        pass


def test_inspection_reports_each_pragma_divergence() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA busy_timeout = 17")

        state = inspect_sqlite_connection(connection)

    assert state.journal_mode == "memory"
    assert state.synchronous == 0
    assert state.foreign_keys == 0
    assert state.busy_timeout_ms == 17
    assert state.readiness_checks(expected_busy_timeout_ms=5_000) == {
        "sqlite_journal_mode": "failed",
        "sqlite_synchronous": "failed",
        "sqlite_foreign_keys": "failed",
        "sqlite_busy_timeout": "failed",
    }


def test_committed_reply_survives_logical_process_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "restart.db"
    first_process = SqliteConversationStore(database_path)
    first_process.initialize()
    assert first_process.get_or_create_reply(_message(), "Resposta persistida") == (
        "Resposta persistida"
    )

    restarted_process = SqliteConversationStore(database_path)
    assert restarted_process.get_or_create_reply(_message(), "Resposta diferente") == (
        "Resposta persistida"
    )


def test_locked_short_write_obeys_bounded_busy_timeout(tmp_path: Path) -> None:
    database_path = tmp_path / "locked.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    blocker = sqlite3.connect(database_path)
    configure_sqlite_connection(
        blocker,
        busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
        set_journal_mode=False,
    )
    blocker.execute("BEGIN IMMEDIATE")

    started_at = monotonic()
    try:
        with pytest.raises(PersistenceUnavailable):
            store.admit_generation(_message(), lock_timeout=0.05)
    finally:
        blocker.rollback()
        blocker.close()

    assert monotonic() - started_at < 0.5
    assert store.admit_generation(_message(), lock_timeout=0.5).inbound_message_id > 0


@pytest.mark.parametrize(
    ("pragma", "value", "failed_check"),
    [
        ("journal_mode", "DELETE", "sqlite_journal_mode"),
        ("synchronous", "OFF", "sqlite_synchronous"),
        ("foreign_keys", "OFF", "sqlite_foreign_keys"),
        ("busy_timeout", "17", "sqlite_busy_timeout"),
    ],
)
def test_readiness_rejects_each_pragma_divergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pragma: str,
    value: str,
    failed_check: str,
) -> None:
    database_path = tmp_path / f"wrong-{pragma}.db"
    store = SqliteConversationStore(database_path)

    def configure_with_divergence(
        connection: sqlite3.Connection,
        *,
        busy_timeout_seconds: float,
        set_journal_mode: bool,
    ) -> None:
        apply_sqlite_connection_pragmas(
            connection,
            busy_timeout_seconds=busy_timeout_seconds,
            set_journal_mode=set_journal_mode,
        )
        connection.execute(f"PRAGMA {pragma} = {value}")

    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            twilio_validate_signature=False,
        ),
        store=store,
    )
    with TestClient(app) as client:
        monkeypatch.setattr(
            "rj_studio_ai.persistence.apply_sqlite_connection_pragmas",
            configure_with_divergence,
        )
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"][failed_check] == "failed"


def test_readiness_rejects_declared_multi_process_sqlite_deployment(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "multi-process.db",
            twilio_validate_signature=False,
            app_process_count=2,
        )
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["sqlite_single_process"] == "failed"
