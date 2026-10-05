import sqlite3

import pytest
from alembic import command
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from test_conversational_intake_migration import legacy_intake

from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import SqliteConversationStore


@pytest.mark.parametrize("interrupt", [False, True])
def test_upgrade_preserves_all_baseline_rows_and_rolls_back_partial_rebuild(tmp_path, interrupt):
    path = tmp_path / "baseline.db"
    config = legacy_intake(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0011_conversational_intake")
        connection.commit()
    engine.dispose()
    tables = [
        "conversations",
        "messages",
        "message_processing",
        "outbound_deliveries",
        "conversation_handoffs",
        "appointment_intakes",
    ]
    with sqlite3.connect(path) as connection:
        before = {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables}

    def fault(connection, cursor, statement, parameters, context, executemany):
        if statement.strip().startswith("DROP TABLE appointment_intakes"):
            raise RuntimeError("injected interruption")

    if interrupt:
        event.listen(Engine, "after_cursor_execute", fault)
    try:
        if interrupt:
            with pytest.raises(RuntimeError, match="injected interruption"):
                MigrationManager(path).upgrade()
        else:
            MigrationManager(path).upgrade()
    finally:
        if interrupt:
            event.remove(Engine, "after_cursor_execute", fault)
    with sqlite3.connect(path) as connection:
        assert {t: connection.execute(f"SELECT * FROM {t}").fetchall() for t in tables} == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        expected = "0011_conversational_intake" if interrupt else "0013_openai_generation_metadata"
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == expected
        )


def test_fresh_schema_has_current_constraints(tmp_path):
    path = tmp_path / "fresh.db"
    SqliteConversationStore(path).initialize()
    assert MigrationManager(path).is_current()
