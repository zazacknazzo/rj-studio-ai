import sqlite3

import pytest
from alembic import command
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from test_conversational_intake_migration import legacy_intake

from rj_studio_ai.migrations import MigrationManager


@pytest.mark.parametrize("interrupt", [False, True])
def test_openai_metrics_upgrade_preserves_old_evidence_and_rolls_back(tmp_path, interrupt):
    path = tmp_path / "baseline.db"
    config = legacy_intake(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0012_agentic_intake")
        connection.commit()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        inbound = connection.execute(
            "SELECT id FROM messages WHERE direction='inbound' LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO generation_metrics (inbound_message_id, attempt_number, provider, "
            "model, configuration, latency_ms, input_tokens, output_tokens, total_tokens, "
            "outcome, created_at) VALUES (?, 1, 'anthropic', 'synthetic', 'thinking=disabled', "
            "100, 20, 10, 30, 'success', '2026-10-05T12:00:00+00:00')",
            (inbound,),
        )
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT IN ('alembic_version', 'sqlite_sequence')"
            )
        ]
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
        }

    def fault(connection, cursor, statement, parameters, context, executemany):
        if "ADD COLUMN reasoning_tokens" in statement:
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
        for table in tables:
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()
            if table == "generation_metrics" and not interrupt:
                assert [row[:-5] for row in rows] == before[table]
                assert rows[0][-5:] == (None,) * 5
            else:
                assert rows == before[table]
        expected = "0012_agentic_intake" if interrupt else "0013_openai_generation_metadata"
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == expected
        )
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        if not interrupt:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE generation_metrics SET incomplete_reason='raw-private-reason'"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("UPDATE generation_metrics SET reasoning_tokens=-1")
    assert MigrationManager(path).is_current() is not interrupt
