import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from rj_studio_ai.migrations import MigrationManager


def _baseline(path):
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/rj_studio_ai/migrations")
    )
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0008_twilio_delivery_status")
        connection.commit()
    engine.dispose()
    with sqlite3.connect(path) as connection:
        now = "2026-10-02T10:00:00+00:00"
        connection.execute(
            "INSERT INTO conversations VALUES (1, 'meta', 'synthetic-customer', ?, ?)", (now, now)
        )
        for index, state in enumerate(["accepted", "pending", "sending", "unknown"], start=1):
            inbound = index * 2 - 1
            outbound = index * 2
            connection.execute(
                "INSERT INTO messages (id, conversation_id, provider, provider_message_id, "
                "recipient_address, "
                "direction, body, created_at) "
                "VALUES (?, 1, 'meta', ?, 'synthetic-channel', 'inbound', ?, ?)",
                (inbound, f"synthetic-{index}", f"inbound-{index}", now),
            )
            connection.execute(
                "INSERT INTO messages (id, conversation_id, provider, direction, body, "
                "created_at, in_reply_to_message_id) "
                "VALUES (?, 1, 'meta', 'outbound', ?, ?, ?)",
                (outbound, f"reply-{index}", now, inbound),
            )
            connection.execute(
                """
                INSERT INTO outbound_deliveries (
                    outbound_message_id, provider, provider_channel_id, recipient_address, state,
                    owner_token, lease_expires_at, attempt_count, next_attempt_at,
                    provider_message_id,
                    safe_error_code, accepted_at, created_at, updated_at
                ) VALUES (?, 'meta', 'synthetic-channel', 'synthetic-customer',
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outbound,
                    state,
                    "owner" if state == "sending" else None,
                    "2026-10-02T10:00:30+00:00" if state == "sending" else None,
                    1 if state == "sending" else 0,
                    now if state == "pending" else None,
                    "wamid.synthetic" if state == "accepted" else None,
                    "legacy_unverified" if state == "unknown" else None,
                    now if state == "accepted" else None,
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE message_processing SET state = 'completed' WHERE inbound_message_id = ?",
                (inbound,),
            )


@pytest.mark.parametrize("failure", [False, True])
def test_upgrade_preserves_m06_data_and_conservatively_marks_ambiguous_submission(
    tmp_path, failure
):
    path = tmp_path / "baseline.db"
    _baseline(path)
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM messages ORDER BY id").fetchall()
        deliveries = connection.execute(
            "SELECT id, state, provider_message_id FROM outbound_deliveries ORDER BY id"
        ).fetchall()
        if failure:
            connection.execute(
                "CREATE TRIGGER ai_reply_rejects_active_handoff BEFORE UPDATE ON messages "
                "WHEN 0 BEGIN SELECT 1; END"
            )
    manager = MigrationManager(path)
    assert not manager.is_current()
    if failure:
        with pytest.raises(SQLAlchemyError):
            manager.upgrade()
    else:
        manager.upgrade()
        manager.upgrade()
        assert manager.is_current()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM messages ORDER BY id").fetchall() == before
        assert (
            connection.execute(
                "SELECT id, state, provider_message_id FROM outbound_deliveries ORDER BY id"
            ).fetchall()
            == deliveries
        )
        if failure:
            assert (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "0008_twilio_delivery_status"
            )
            assert "submission_started_at" not in {
                row[1] for row in connection.execute("PRAGMA table_info(outbound_deliveries)")
            }
        else:
            assert (
                connection.execute("SELECT COUNT(*) FROM conversation_handoffs").fetchone()[0] == 0
            )
            rows = connection.execute(
                "SELECT state, submission_started_at FROM outbound_deliveries ORDER BY id"
            ).fetchall()
            assert rows == [
                ("accepted", None),
                ("pending", None),
                ("sending", "2026-10-02T10:00:00+00:00"),
                ("unknown", "2026-10-02T10:00:00+00:00"),
            ]
