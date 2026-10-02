import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore


def baseline(path):
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/rj_studio_ai/migrations")
    )
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0009_durable_human_handoff")
        connection.commit()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    store = SqliteConversationStore(path)
    claim = store.claim_generation(
        InboundMessage(
            "meta",
            "wamid.synthetic",
            "synthetic-customer",
            "synthetic-channel",
            "synthetic inbound",
        )
    )
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="synthetic reply",
        delivery_state=DeliveryState.PENDING,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO conversation_handoffs VALUES (1, 1, 'synthetic-episode', "
            "'explicit_human_request', '2026-10-02T10:00:00+00:00', NULL)"
        )
    return config


@pytest.mark.parametrize("failing_upgrade", [False, True])
def test_upgrade_preserves_all_existing_data_and_rolls_back_ddl_failure(tmp_path, failing_upgrade):
    path = tmp_path / "baseline.db"
    baseline(path)
    tables = (
        "conversations",
        "messages",
        "message_processing",
        "outbound_deliveries",
        "conversation_handoffs",
    )
    with sqlite3.connect(path) as connection:
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
        }
        if failing_upgrade:
            connection.execute("CREATE TABLE appointment_intakes (occupied TEXT)")
    manager = MigrationManager(path)
    assert not manager.is_current()
    if failing_upgrade:
        with pytest.raises(SQLAlchemyError):
            manager.upgrade()
    else:
        manager.upgrade()
        manager.upgrade()
        assert manager.is_current()
    with sqlite3.connect(path) as connection:
        assert {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
        } == before
        if failing_upgrade:
            assert (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "0009_durable_human_handoff"
            )
        else:
            assert connection.execute("SELECT count(*) FROM appointment_intakes").fetchone()[0] == 0
            assert (
                connection.execute("SELECT state FROM outbound_deliveries").fetchone()[0]
                == "pending"
            )


def test_fresh_migration_has_readiness_constraints_and_rejects_destructive_downgrade(tmp_path):
    path = tmp_path / "fresh.db"
    store = SqliteConversationStore(path)
    store.initialize()
    assert MigrationManager(path).is_current()
    claim = store.claim_generation(
        InboundMessage(
            "meta",
            "wamid.synthetic",
            "synthetic-customer",
            "synthetic-channel",
            "synthetic inbound",
        )
    )
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM appointment_intakes").fetchone()[0] == 0
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/rj_studio_ai/migrations")
    )
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="backup/restore"):
            command.downgrade(config, "0009_durable_human_handoff")
    engine.dispose()
    assert MigrationManager(path).is_current()
    assert (
        store.get_generation(
            provider="meta", provider_message_id="wamid.synthetic"
        ).inbound_message_id
        == claim.inbound_message_id
    )


@pytest.mark.parametrize(
    "column,value",
    [
        ("state", "appointment"),
        ("clarification_count", -1),
        ("clarification_count", 3),
        ("clarification_count", 1.5),
        ("desired_service", "x" * 121),
        ("preferred_time", ""),
        ("professional_preference", " padded "),
        ("awaiting_field", None),
        ("handoff_token", "unsolicited-token"),
        ("episode_token", ""),
    ],
)
def test_database_rejects_invalid_intake_shapes(tmp_path, column, value):
    path = tmp_path / "constraints.db"
    store = SqliteConversationStore(path)
    store.initialize()
    store.admit_generation(
        InboundMessage(
            "meta",
            "wamid.synthetic",
            "synthetic-customer",
            "synthetic-channel",
            "synthetic inbound",
        )
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO appointment_intakes VALUES (1, 'synthetic-episode', 'collecting', "
            "NULL, NULL, NULL, 1, 'desired_service', 1, NULL, '2026-10-02T10:00:00+00:00')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f"UPDATE appointment_intakes SET {column} = ?", (value,))


def test_readiness_rejects_missing_intake_schema(tmp_path):
    path = tmp_path / "readiness.db"
    store = SqliteConversationStore(path)
    store.initialize()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE appointment_intakes")
    assert not MigrationManager(path).is_current()
