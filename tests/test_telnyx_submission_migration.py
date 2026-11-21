"""Additive migration/restore evidence from the exact pre-Ticket10 schema."""

import sqlite3
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import event
from sqlalchemy.engine import Engine
from telnyx_channel_fixture import verified_channel, verified_consent
from test_telnyx_authentication import PHONE
from test_telnyx_messages import CUSTOMER, TIME

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.whatsapp_policy import payload_fingerprint


def baseline(path, monkeypatch, *, outcome="retryable"):
    manager = MigrationManager(path)
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda config, _: original(config, "0020_channel_lifecycle")
        )
        manager.upgrade()
    verified_channel(path)
    timestamp = TIME.isoformat()
    lease = TIME.replace(year=TIME.year + 1).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for index, provider in enumerate(("telnyx", "meta", "twilio"), start=1):
            inbound, outbound = index * 2 - 1, index * 2
            connection.execute(
                "INSERT INTO conversations(id,provider,customer_address,created_at,updated_at) "
                "VALUES(?,?,?,?,?)",
                (index, provider, CUSTOMER, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO messages(id,conversation_id,provider,provider_message_id,"
                "recipient_address,direction,body,created_at) VALUES(?,?,?,?,?,'inbound',?,?)",
                (
                    inbound,
                    index,
                    provider,
                    f"historical-{provider}",
                    PHONE,
                    "Synthetic input",
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO messages(id,conversation_id,provider,recipient_address,direction,"
                "body,created_at,in_reply_to_message_id) VALUES(?,?,?,?,'outbound',?,?,?)",
                (outbound, index, provider, CUSTOMER, "Synthetic reply", timestamp, inbound),
            )
            connection.execute(
                "INSERT INTO outbound_deliveries(id,outbound_message_id,provider,"
                "provider_channel_id,"
                "recipient_address,state,attempt_count,next_attempt_at,created_at,updated_at) "
                "VALUES(?,?,?,?,?,'pending',0,?,?,?)",
                (index, outbound, provider, PHONE, CUSTOMER, timestamp, timestamp, timestamp),
            )
            connection.execute(
                "UPDATE message_processing SET state='completed' WHERE inbound_message_id=?",
                (inbound,),
            )
            if outcome == "pending":
                continue
            connection.execute(
                "UPDATE outbound_deliveries SET state='sending',owner_token=?,lease_expires_at=?,"
                "attempt_count=1,next_attempt_at=NULL,submission_started_at=? WHERE id=?",
                (f"owner-{provider}", lease, timestamp, index),
            )
            connection.execute(
                "INSERT INTO delivery_attempts(outbound_delivery_id,attempt_number,owner_token,"
                "outcome,started_at) VALUES(?,1,?,'started',?)",
                (index, f"owner-{provider}", timestamp),
            )
            accepted = outcome == "accepted"
            message_id = f"accepted-{provider}" if accepted else None
            error = None if accepted else "historical_result"
            connection.execute(
                "UPDATE delivery_attempts SET outcome=?,provider_message_id=?,safe_error_code=?,"
                "completed_at=? WHERE outbound_delivery_id=?",
                (outcome, message_id, error, timestamp, index),
            )
            connection.execute(
                "UPDATE outbound_deliveries SET state=?,owner_token=NULL,lease_expires_at=NULL,"
                "next_attempt_at=?,provider_message_id=?,safe_error_code=?,accepted_at=? "
                "WHERE id=?",
                (
                    outcome,
                    timestamp if outcome == "retryable" else None,
                    message_id,
                    error,
                    timestamp if accepted else None,
                    index,
                ),
            )
        connection.execute(
            "INSERT INTO inbound_event_receipts(provider,channel_id,customer_address,event_id,"
            "provider_message_id,occurred_at,message_occurred_at,aliases_json,received_at) "
            "VALUES('telnyx',?,?,'historical-event','historical-telnyx',?,?,'[]',?)",
            (PHONE, CUSTOMER, timestamp, timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO pending_delivery_statuses(provider,provider_message_id,status,received_at,"
            "updated_at) VALUES('twilio','legacy-status','read',?,?)",
            (timestamp, timestamp),
        )
    return manager


def snapshot(path):
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name!='alembic_version' ORDER BY name"
            )
        ]
        columns = {
            table: [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            for table in tables
        }
        data = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
    return columns, data


def assert_preserved(path, before):
    columns, data = before
    with sqlite3.connect(path) as connection:
        for table, names in columns.items():
            # Explicit historical columns ensure additive fields cannot hide changed evidence.
            assert (
                connection.execute(f"SELECT {','.join(names)} FROM {table}").fetchall()
                == data[table]
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def backup(source, destination):
    with sqlite3.connect(source) as original, sqlite3.connect(destination) as restored:
        original.backup(restored)


@pytest.mark.parametrize("outcome", ["pending", "retryable", "unknown", "accepted"])
def test_upgrade_from_0020_backfills_only_identity_and_preserves_all_history(
    tmp_path, monkeypatch, outcome
):
    path = tmp_path / "baseline.db"
    manager = baseline(path, monkeypatch, outcome=outcome)
    before = snapshot(path)
    pre_upgrade = tmp_path / "backup-0020.db"
    backup(path, pre_upgrade)
    manager.upgrade()
    assert manager.is_current()
    assert_preserved(path, before)
    with sqlite3.connect(path) as connection:
        identities = connection.execute(
            "SELECT provider,submission_key,payload_fingerprint,first_submission_at "
            "FROM outbound_deliveries ORDER BY id"
        ).fetchall()
        assert UUID(identities[0][1]).version == 4
        assert identities[0][2] == payload_fingerprint(
            OutboundMessage(PHONE, CUSTOMER, "Synthetic reply")
        )
        assert identities[0][3] is None
        assert identities[1:] == [("meta", None, None, None), ("twilio", None, None, None)]
        assert connection.execute(
            "SELECT submission_started_at,retry_evidence FROM delivery_attempts"
        ).fetchall() == [(None, None)] * (0 if outcome == "pending" else 3)
    manager.upgrade()
    assert SqliteConversationStore(path).get_delivery(1).submission_key == identities[0][1]
    post_upgrade = tmp_path / "backup-0021.db"
    backup(path, post_upgrade)
    SqliteConversationStore(post_upgrade).initialize()
    assert SqliteConversationStore(post_upgrade).get_delivery(1).submission_key == identities[0][1]
    assert_preserved(post_upgrade, before)
    MigrationManager(pre_upgrade).upgrade()
    assert_preserved(pre_upgrade, before)
    assert UUID(SqliteConversationStore(pre_upgrade).get_delivery(1).submission_key).version == 4


def test_historical_retry_without_proof_does_not_gain_submission_authority(tmp_path, monkeypatch):
    path = tmp_path / "historical-retry.db"
    manager = baseline(path, monkeypatch)
    manager.upgrade()
    verified_consent(path, customer=CUSTOMER, now=TIME)
    store = SqliteConversationStore(path)
    claim = store.claim_next_delivery(provider="telnyx", now=TIME)
    assert claim.state is DeliveryState.SENDING
    assessment = store.assess_telnyx_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        now=TIME,
    )
    assert not assessment.eligible
    assert assessment.decision.reason == "historical_submission_unproven"
    assert not store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        now=TIME,
    )
    assert store.get_delivery(1).first_submission_at is None
    assert store.get_delivery_attempts(1)[0].retry_evidence is None


def test_historical_terminal_attempt_cannot_gain_retroactive_submission_proof(
    tmp_path, monkeypatch
):
    path = tmp_path / "historical-proof.db"
    manager = baseline(path, monkeypatch)
    manager.upgrade()
    with sqlite3.connect(path) as connection:
        before = connection.execute("SELECT * FROM delivery_attempts").fetchall()
        for assignment in (
            "retry_evidence='not_submitted'",
            "submission_started_at='2026-01-01T00:00:00+00:00'",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="requires current claim"):
                connection.execute(
                    f"UPDATE delivery_attempts SET {assignment} WHERE outbound_delivery_id=1"
                )
        assert connection.execute("SELECT * FROM delivery_attempts").fetchall() == before


@pytest.mark.parametrize(
    "stage", ["ADD COLUMN first_submission_at", "CREATE TRIGGER telnyx_submission_identity_insert"]
)
def test_failed_migration_rolls_back_schema_backfill_and_data(tmp_path, monkeypatch, stage):
    path = tmp_path / "failed-migration.db"
    manager = baseline(path, monkeypatch)
    before = snapshot(path)

    def fail(connection, cursor, statement, parameters, context, many):
        if stage in statement:
            raise RuntimeError("synthetic migration failure")

    event.listen(Engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic migration failure"):
            manager.upgrade()
    finally:
        event.remove(Engine, "after_cursor_execute", fail)
    assert snapshot(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0020_channel_lifecycle",
        )
    manager.upgrade()
    assert manager.is_current()
    assert_preserved(path, before)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("telnyx_submission_identity_immutable", "TRIGGER"),
        ("telnyx_submission_rejects_replacement", "TRIGGER"),
        ("telnyx_clock_monotonic", "TRIGGER"),
        ("telnyx_attempt_rejects_replacement", "TRIGGER"),
        ("telnyx_attempt_initial_evidence", "TRIGGER"),
        ("telnyx_attempt_evidence_requires_current_claim", "TRIGGER"),
        ("uq_delivery_submission_key", "INDEX"),
    ],
)
def test_new_schema_guards_are_required_for_structural_readiness(tmp_path, name, kind):
    path = tmp_path / "schema-damage.db"
    manager = MigrationManager(path)
    manager.upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP {kind} {name}")
    assert not manager.is_current()
