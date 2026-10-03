import sqlite3

import pytest
from alembic import command
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from test_appointment_intake_migration import baseline

from rj_studio_ai.migrations import MigrationManager


def legacy_intake(path):
    config = baseline(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0010_appointment_intake")
        connection.commit()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO appointment_intakes VALUES (1, 'old-episode', 'handoff', "
            "'corte', 'sexta à tarde', 'Ana', 2, NULL, 1, 'synthetic-episode', "
            "'2026-10-02T10:00:00+00:00')"
        )
    return config


@pytest.mark.parametrize("fail_after_table_replacement", [False, True])
def test_polish_upgrade_preserves_legacy_state_or_rolls_back_replacement(
    tmp_path, fail_after_table_replacement
):
    path = tmp_path / "legacy.db"
    legacy_intake(path)
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
            raise RuntimeError("injected migration interruption")

    manager = MigrationManager(path)
    if fail_after_table_replacement:
        event.listen(Engine, "after_cursor_execute", fault)
        try:
            with pytest.raises(RuntimeError, match="injected"):
                manager.upgrade()
        finally:
            event.remove(Engine, "after_cursor_execute", fault)
    else:
        manager.upgrade()
        manager.upgrade()
        assert manager.is_current()
    with sqlite3.connect(path) as connection:
        for table in tables:
            actual = connection.execute(f"SELECT * FROM {table}").fetchall()
            if table == "appointment_intakes" and not fail_after_table_replacement:
                assert [r[:11] for r in actual] == before[table]
                assert actual[0][11:] == (None, "interest", 0)
            else:
                assert actual == before[table]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute("SELECT state FROM outbound_deliveries").fetchone()[0] == "pending"
        )
        if fail_after_table_replacement:
            assert (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "0010_appointment_intake"
            )


@pytest.mark.parametrize(
    "column,value",
    [
        ("preferred_day", " padded "),
        ("request_kind", "crm"),
        ("recovery_offered", 2),
        ("clarification_count", 4),
        ("awaiting_field", "availability"),
    ],
)
def test_new_intake_constraints_enforced_in_database(tmp_path, column, value):
    path = tmp_path / "constraints.db"
    legacy_intake(path)
    MigrationManager(path).upgrade()
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(f"UPDATE appointment_intakes SET {column} = ?", (value,))
