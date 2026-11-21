"""0022 is additive and transactionally preserves exact Ticket10 history."""

import sqlite3

import pytest
from alembic import command
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from test_telnyx_submission_migration import assert_preserved, backup, baseline, snapshot

from rj_studio_ai.migrations import MigrationManager


@pytest.mark.parametrize("outcome", ["pending", "unknown", "accepted", "retryable"])
def test_0021_upgrade_preserves_history_without_inventing_request_proof(
    tmp_path, monkeypatch, outcome
):
    path = tmp_path / "historical.db"
    manager = baseline(path, monkeypatch, outcome=outcome)
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda cfg, _: original(cfg, "0021_telnyx_submission_policy")
        )
        manager.upgrade()
    before = snapshot(path)
    old = tmp_path / "backup-0021.db"
    backup(path, old)
    manager.upgrade()
    assert manager.is_current()
    assert_preserved(path, before)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []
    restored = MigrationManager(old)
    restored.upgrade()
    assert restored.is_current()
    assert_preserved(old, before)


def test_0022_failure_rolls_back_all_ddl_and_history(tmp_path, monkeypatch):
    path = tmp_path / "historical.db"
    manager = baseline(path, monkeypatch, outcome="accepted")
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda cfg, _: original(cfg, "0021_telnyx_submission_policy")
        )
        manager.upgrade()
    before = snapshot(path)

    def fail(_, __, statement, *___):
        if "CREATE TRIGGER telnyx_http_reject_replace" in statement:
            raise sqlite3.OperationalError("synthetic migration interruption")

    event.listen(Engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(OperationalError, match="synthetic migration interruption"):
            manager.upgrade()
    finally:
        event.remove(Engine, "before_cursor_execute", fail)
    assert_preserved(path, before)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0021_telnyx_submission_policy",
        )
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'telnyx_http%'").fetchall()
            == []
        )
    manager.upgrade()
    assert manager.is_current()


@pytest.mark.parametrize(
    "name,kind",
    [
        ("telnyx_http_requests", "TABLE"),
        ("telnyx_http_reject_update", "TRIGGER"),
        ("telnyx_http_reject_delete", "TRIGGER"),
        ("telnyx_http_reject_replace", "TRIGGER"),
        ("telnyx_http_reject_key_reuse", "TRIGGER"),
    ],
)
def test_damaged_http_identity_fails_schema_readiness(tmp_path, name, kind):
    path = tmp_path / "synthetic.db"
    manager = MigrationManager(path)
    manager.upgrade()
    assert manager.is_current()
    with sqlite3.connect(path) as db:
        db.execute(f"DROP {kind} {name}")
    assert not manager.is_current()
