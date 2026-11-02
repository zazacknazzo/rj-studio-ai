"""Temporary databases and canonical synthetic events only; no provider wire integration."""

import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta, timezone
from threading import Barrier

import pytest
from alembic import command
from fastapi.testclient import TestClient
from test_async_ingress import _PausedExecutor
from test_coexistence_contracts import (
    NOW,
    _CanonicalFixtureAdapter,
    _NoGeneration,
    delivery_status,
    edit,
    human,
    inbound,
    lifecycle,
    revoke,
)
from test_migrations import V01_SCHEMA_WITH_DATA

from rj_studio_ai.config import Settings
from rj_studio_ai.domain import (
    ChannelScope,
    MessageReference,
)
from rj_studio_ai.main import create_app
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / "journal.db"
    store = SqliteConversationStore(path)
    store.initialize()
    return store, path


def rows(path, table="operational_events"):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def identified(event, event_id):
    return replace(event, metadata=replace(event.metadata, event_id=event_id))


def aliased(event):
    return replace(
        event,
        metadata=replace(
            event.metadata,
            message_aliases=(
                MessageReference("upstream", "alias-synthetic"),
                MessageReference("secondary", "alias-synthetic"),
            ),
            message_occurred_at=NOW - timedelta(minutes=1),
        ),
    )


@pytest.mark.parametrize("make_event", [human, edit, revoke, lifecycle])
def test_identical_duplicate_keeps_first_receipt_and_has_no_work(journal, make_event):
    store, path = journal
    event = make_event()
    store.record_webhook_events((event, event), now=NOW)
    store.record_webhook_events((event,), now=NOW + timedelta(days=10))
    assert len(rows(path)) == 1
    assert rows(path)[0]["received_at"] == NOW.isoformat()
    assert len(rows(path, "conversations")) == (1 if make_event is human else 0)
    for table in (
        "messages",
        "message_processing",
        "outbound_deliveries",
        "conversation_handoffs",
        "pending_delivery_statuses",
    ):
        assert rows(path, table) == []


def test_event_id_is_scoped_by_provider_kind_and_resource(journal):
    store, path = journal
    events = (
        human(),
        replace(human(), provider="second-provider"),
        replace(human(), channel_id="second-channel"),
        replace(lifecycle(), scope_id="studio"),
        replace(lifecycle(), scope_id="another-account"),
    )
    store.record_webhook_events(events)
    assert len(rows(path)) == 5
    # A channel lifecycle event shares the event scope with a Message event.
    with pytest.raises(ValueError, match="Conflicting canonical"):
        store.record_webhook_events(
            (replace(lifecycle(), scope=ChannelScope.CHANNEL, scope_id="studio"),)
        )
    assert len(rows(path)) == 5


def test_distinct_events_sharing_message_original_or_alias_are_preserved(journal):
    store, path = journal
    events = (
        aliased(human()),
        identified(aliased(human()), "second-echo"),
        identified(aliased(edit()), "edit-event"),
        identified(aliased(revoke()), "revoke-event"),
    )
    store.record_webhook_events(events)
    assert len(rows(path)) == 4
    assert len(rows(path, "operational_event_aliases")) == 8
    assert rows(path)[0]["provider_message_id"] == rows(path)[1]["provider_message_id"]
    assert rows(path)[2]["original_message_id"] == "message-customer"
    assert rows(path)[3]["original_namespace"] == "upstream"
    assert rows(path, "messages") == []  # No invented target from a matching alias.


def test_alias_order_duplicates_and_equivalent_timezones_are_not_new_events(journal):
    store, path = journal
    event = aliased(human())
    store.record_webhook_events((event,))
    metadata = replace(
        event.metadata,
        message_aliases=tuple(reversed(event.metadata.message_aliases)) * 2,
        occurred_at=NOW.astimezone(timezone(timedelta(hours=-3))),
    )
    store.record_webhook_events((replace(event, metadata=metadata),))
    assert len(rows(path)) == 1
    assert len(rows(path, "operational_event_aliases")) == 2
    assert rows(path)[0]["message_occurred_at"] == (NOW - timedelta(minutes=1)).isoformat()


@pytest.mark.parametrize(
    "change",
    [
        lambda e: replace(e, customer_address="other-customer"),
        lambda e: replace(e, provider_message_id="other-message"),
        lambda e: replace(e, metadata=replace(e.metadata, occurred_at=NOW - timedelta(seconds=1))),
        lambda e: aliased(e),
    ],
)
def test_conflicting_duplicate_rolls_back_prior_rows_in_batch(journal, change):
    store, path = journal
    store.record_webhook_events((human(),))
    with pytest.raises(ValueError, match="Conflicting canonical"):
        store.record_webhook_events((inbound(), identified(edit(), "new-edit"), change(human())))
    assert len(rows(path)) == 1
    for table in ("messages", "message_processing", "operational_event_aliases"):
        assert rows(path, table) == []


def test_out_of_order_revocation_original_and_lifecycle_remain_observations(journal):
    store, path = journal
    older = identified(
        replace(
            lifecycle(), metadata=replace(lifecycle().metadata, occurred_at=NOW - timedelta(days=2))
        ),
        "older-lifecycle",
    )
    store.record_webhook_events((revoke(), lifecycle(), older))
    store.record_webhook_events((inbound(), identified(human(), "later-echo")))
    assert [row["kind"] for row in rows(path)] == [
        "message_revocation",
        "channel_lifecycle",
        "channel_lifecycle",
        "human_activity",
    ]
    assert rows(path)[2]["occurred_at"] < rows(path)[1]["occurred_at"]
    assert len(rows(path, "messages")) == 1
    assert rows(path, "message_processing")[0]["state"] == "suppressed"


def test_mixed_batch_commits_old_paths_and_all_operational_kinds(journal):
    store, path = journal
    events = (
        inbound(),
        delivery_status(),
        human(),
        identified(edit(), "edit"),
        identified(revoke(), "revoke"),
        lifecycle(),
    )
    store.record_webhook_events(events)
    store.record_webhook_events(events)
    assert len(rows(path)) == 4
    assert len(rows(path, "messages")) == len(rows(path, "message_processing")) == 1
    assert rows(path, "pending_delivery_statuses")[0]["status"] == "delivered"
    assert rows(path, "outbound_deliveries") == []  # Status does not create acceptance.


@pytest.mark.parametrize("bad", [object(), {"body": "synthetic"}, None])
def test_invalid_batch_never_partially_admits_work(journal, bad):
    store, path = journal
    with pytest.raises(ValueError, match="Unsupported canonical"):
        store.record_webhook_events((inbound(), human(), bad))
    assert rows(path) == rows(path, "messages") == []


def test_sql_failure_after_journal_insert_rolls_back_every_table(journal):
    store, path = journal
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER synthetic_failure
            BEFORE INSERT ON operational_event_aliases
            BEGIN SELECT RAISE(ABORT, 'synthetic-private-sentinel'); END""")
    with pytest.raises(PersistenceUnavailable) as caught:
        store.record_webhook_events((inbound(), delivery_status(), aliased(human())))
    assert "synthetic-private-sentinel" not in "".join(traceback.format_exception(caught.value))
    for table in (
        "messages",
        "message_processing",
        "operational_events",
        "operational_event_aliases",
        "pending_delivery_statuses",
    ):
        assert rows(path, table) == []


def test_concurrent_duplicate_writers_commit_one_receipt(journal):
    store, path = journal
    barrier = Barrier(4)

    def write():
        writer = SqliteConversationStore(path)
        barrier.wait(timeout=5)
        writer.record_webhook_events((inbound(), aliased(human())), now=NOW)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: write(), range(4)))
    assert len(rows(path)) == len(rows(path, "messages")) == 1
    assert len(rows(path, "operational_event_aliases")) == 2


def test_lock_failure_is_retryable_and_leaves_no_receipt(journal):
    store, path = journal
    with sqlite3.connect(path) as lock:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(PersistenceUnavailable):
            store.record_webhook_events((inbound(), human()), lock_timeout=0)
    assert rows(path) == rows(path, "messages") == []
    store.record_webhook_events((inbound(), human()))
    assert len(rows(path)) == len(rows(path, "messages")) == 1


def test_restart_replay_and_explicit_message_purge_preserve_operational_evidence(journal):
    store, path = journal
    old = NOW - timedelta(days=400)
    store.record_webhook_events((aliased(human()),), now=old)
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    restarted.purge_messages_older_than(NOW)
    with pytest.raises(PersistenceUnavailable):
        restarted.delete_conversation(provider="synthetic", customer_address="customer")
    restarted.record_webhook_events((aliased(human()),), now=NOW)
    assert len(rows(path)) == 1
    assert rows(path)[0]["received_at"] == old.isoformat()
    assert len(rows(path, "operational_event_aliases")) == 2


class _AckObserver(_CanonicalFixtureAdapter):
    def __init__(self, path):
        super().__init__(aliased(human()))
        self.path = path
        self.acks = 0

    def acknowledge(self):
        # Separate connection proves the entire observation committed before ACK.
        assert len(rows(self.path)) == 1
        assert len(rows(self.path, "operational_event_aliases")) == 2
        self.acks += 1
        return super().acknowledge()


@pytest.mark.parametrize("failure", ["none", "statement", "commit"])
def test_ack_only_after_successful_commit_without_generation(journal, monkeypatch, failure, caplog):
    store, path = journal
    adapter = _AckObserver(path)
    processor = _PausedExecutor()
    sender = DeterministicFakeOutboundSender(outcomes=[])
    app = create_app(
        Settings(_env_file=None, database_path=path, delivery_mode="proactive"),
        provider=adapter,
        store=store,
        generator=_NoGeneration(),
        outbound_sender=sender,
        processing_executor=processor,
    )
    with TestClient(app) as client:
        if failure == "statement":
            with sqlite3.connect(path) as connection:
                connection.execute("""CREATE TRIGGER synthetic_failure BEFORE INSERT ON
                    operational_event_aliases BEGIN
                    SELECT RAISE(ABORT, 'private-customer-identifier'); END""")
        elif failure == "commit":
            original = store._connect

            @contextmanager
            def failed_commit(*args, **kwargs):
                with original(*args, **kwargs) as connection:
                    # SQLite's deferred FK is checked at real COMMIT, after all INSERTs.
                    connection.execute("PRAGMA defer_foreign_keys = ON")
                    yield connection
                    if connection.in_transaction:
                        connection.execute(
                            "INSERT INTO operational_event_aliases VALUES "
                            "(-1, 'synthetic', 'commit-failure')"
                        )

            monkeypatch.setattr(store, "_connect", failed_commit)
        response = client.post("/webhooks/whatsapp", json={})
        assert response.status_code == (200 if failure == "none" else 503)
    assert adapter.acks == (1 if failure == "none" else 0)
    assert processor.wakes == 0
    assert sender.calls == []
    assert rows(path, "messages") == []
    assert len(rows(path)) == (1 if failure == "none" else 0)
    assert "private-customer-identifier" not in caplog.text + response.text


def test_legacy_upgrade_preserves_every_existing_row_and_unknown(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(V01_SCHEMA_WITH_DATA)
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command,
            "upgrade",
            lambda config, _: original(config, "0013_openai_generation_metadata"),
        )
        MigrationManager(path).upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute("""INSERT INTO conversation_handoffs VALUES
                           (7, 1, 'synthetic-owner', 'synthetic-reason', '2026-01-01', NULL)""")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'alembic_version'"
            )
        ]
    before = {table: rows(path, table) for table in tables}
    store = SqliteConversationStore(path)
    store.initialize()
    after = {table: rows(path, table) for table in tables}
    for row in after["message_processing"]:
        assert row.pop("automation_revision") == 0
    assert after == before
    assert rows(path, "outbound_deliveries")[0]["state"] == "unknown"
    assert rows(path) == rows(path, "operational_event_aliases") == []
    assert store.migrations_are_current()
    assert all(value == "ok" for value in store.sqlite_durability_checks().values())
    store.record_webhook_events((human(),))
    with pytest.raises(PersistenceUnavailable):
        store.purge_messages_older_than(NOW)
    assert rows(path, "conversation_handoffs")[0]["active"] == 1
    assert rows(path, "outbound_deliveries")[0]["state"] == "unknown"
    assert len(rows(path)) == 1


@pytest.mark.parametrize(
    "index",
    [
        "uq_operational_event_scope",
        "ix_operational_message",
        "uq_operational_alias",
        "ix_operational_alias_reference",
    ],
)
def test_readiness_requires_journal_indexes(journal, index):
    store, path = journal
    assert store.migrations_are_current()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP INDEX {index}")
    assert not store.migrations_are_current()


def test_journal_contains_no_body_or_payload_and_logs_no_identifiers(journal, caplog):
    store, path = journal
    event = replace(
        human(),
        provider_message_id="PRIVATE-MESSAGE-SENTINEL",
        customer_address="PRIVATE-CUSTOMER-SENTINEL",
    )
    store.record_webhook_events((event,))
    with pytest.raises(ValueError) as caught:
        store.record_webhook_events((replace(event, customer_address="PRIVATE-OTHER-SENTINEL"),))
    for marker in (
        "PRIVATE-MESSAGE-SENTINEL",
        "PRIVATE-CUSTOMER-SENTINEL",
        "PRIVATE-OTHER-SENTINEL",
    ):
        assert marker not in caplog.text + str(caught.value)
    assert not {"body", "payload", "raw_payload", "text"}.intersection(rows(path)[0])


@pytest.mark.parametrize("same_identity", [False, True])
def test_concurrent_distinct_events_or_identity_conflict_never_overwrite(journal, same_identity):
    _, path = journal
    barrier = Barrier(2)
    events = (human(), replace(human(), provider_message_id="other-message"))
    if not same_identity:
        events = (events[0], identified(events[1], "other-event"))

    def write(event):
        barrier.wait(timeout=5)
        try:
            SqliteConversationStore(path).record_webhook_events((event,))
        except ValueError:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, events))
    assert outcomes.count("committed") == (1 if same_identity else 2)
    assert outcomes.count("conflict") == (1 if same_identity else 0)
    assert len(rows(path)) == (1 if same_identity else 2)


def test_lost_ack_then_restart_replay_preserves_first_observation(journal):
    store, path = journal
    adapter = _AckObserver(path)

    def lost_ack():
        assert len(rows(path)) == 1
        raise RuntimeError("synthetic lost acknowledgement")

    adapter.acknowledge = lost_ack
    app = create_app(
        Settings(_env_file=None, database_path=path, delivery_mode="proactive"),
        provider=adapter,
        store=store,
        generator=_NoGeneration(),
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/webhooks/whatsapp", json={}).status_code == 500
    before = rows(path)
    reopened = SqliteConversationStore(path)
    reopened.initialize()
    reopened.record_webhook_events((aliased(human()),))
    assert rows(path) == before
    assert rows(path, "messages") == []


def test_foreign_keys_uniqueness_and_shapes_are_enforced(journal):
    store, path = journal
    store.record_webhook_events((aliased(human()), lifecycle()))
    with store._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO operational_event_aliases VALUES (-1, 'ns', 'id')")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO operational_event_aliases "
                "SELECT * FROM operational_event_aliases LIMIT 1"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE operational_events SET event_id = ''")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE operational_events SET availability = 'active' "
                "WHERE kind = 'channel_lifecycle'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE operational_events SET provider_message_id = NULL "
                "WHERE kind = 'human_activity'"
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_failure_rolls_back_schema_and_version(tmp_path, monkeypatch):
    from sqlalchemy import event as sqlalchemy_event
    from sqlalchemy.engine import Engine

    path = tmp_path / "migration-failure.db"
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command,
            "upgrade",
            lambda config, _: original(config, "0013_openai_generation_metadata"),
        )
        MigrationManager(path).upgrade()

    def fault(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().startswith("CREATE TABLE operational_event_aliases"):
            raise RuntimeError("synthetic migration interruption")

    sqlalchemy_event.listen(Engine, "after_cursor_execute", fault)
    try:
        with pytest.raises(RuntimeError, match="synthetic migration interruption"):
            MigrationManager(path).upgrade()
    finally:
        sqlalchemy_event.remove(Engine, "after_cursor_execute", fault)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0013_openai_generation_metadata"
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'operational_%'"
            ).fetchall()
            == []
        )
    MigrationManager(path).upgrade()
    assert MigrationManager(path).is_current()
