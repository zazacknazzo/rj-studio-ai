"""Operational generation pause, using synthetic canonical values and real temporary SQLite."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from threading import Barrier, Event

import pytest
from alembic import command
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import Engine
from test_async_ingress import _BlockingGenerator
from test_coexistence_contracts import NOW, edit, human, inbound, lifecycle, revoke
from test_human_handoff import _activate
from test_operational_event_journal import aliased, identified, rows

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.domain import MessageReference
from rj_studio_ai.generation import FixedReplyGenerator
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.operational_events import record_operational_event
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationRecoveryNotAvailable,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.processing import ProcessingRunner


@pytest.fixture
def pausedb(tmp_path):
    path = tmp_path / "pause.db"
    store = SqliteConversationStore(path)
    store.initialize()
    return store, path


def pause(store, event=None, now=NOW):
    store.record_webhook_events((event or human(),), now=now)


def complete(store, claim, now=NOW, **kwargs):
    return store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Synthetic reply",
        delivery_state=DeliveryState.PENDING,
        now=now,
        **kwargs,
    )


def controls(path):
    return rows(path, "conversation_automation_controls")


def runner(store, generator=None):
    return ProcessingRunner(
        store,
        MessageResponder(
            store=store,
            generator=generator or FixedReplyGenerator("Synthetic reply"),
            safe_failure_reply="Synthetic safe reply",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    )


@pytest.mark.parametrize("admit_first", [False, True])
def test_pause_before_claim_and_before_first_message(pausedb, admit_first):
    store, path = pausedb
    if admit_first:
        store.admit_generation(inbound(), now=NOW)
    pause(store)
    claim = store.claim_generation(inbound(), now=NOW)
    assert not claim.acquired
    assert claim.state is GenerationState.SUPPRESSED
    assert claim.attempt_count == 0
    assert len(controls(path)) == 1
    assert controls(path)[0]["revision"] == 1
    assert store.list_pending_generations(now=NOW) == []
    assert rows(path, "outbound_deliveries") == []
    assert runner(store).run_once() is None


def test_pause_during_llm_does_not_hold_sqlite_lock_or_persist_reply(pausedb, caplog):
    store, path = pausedb
    message = replace(inbound(), body="PRIVATE-CONTENT-SENTINEL")
    store.record_webhook_events((message,))
    generator = _BlockingGenerator()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner(store, generator).run_once)
        try:
            assert generator.entered.wait(timeout=5)
            # A separate writer succeeds while the LLM is blocked, without waiting on its return.
            pause(SqliteConversationStore(path), now=None)
            assert rows(path, "message_processing")[0]["owner_token"] is None
        finally:
            generator.release.set()
        assert future.result(timeout=5) is None
    assert len(rows(path, "messages")) == 1
    assert rows(path, "outbound_deliveries") == []
    assert "PRIVATE-CONTENT-SENTINEL" not in caplog.text


@pytest.mark.parametrize("attempts", [1, 2])
@pytest.mark.parametrize("retryable", [False, True])
def test_pause_invalidates_existing_attempts_and_recovery(pausedb, attempts, retryable):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    if attempts == 2:
        assert store.mark_generation_retryable(
            inbound_message_id=claim.inbound_message_id, owner_token=claim.owner_token, now=NOW
        )
        claim = store.claim_generation(inbound(), now=NOW)
    if retryable:
        assert store.mark_generation_retryable(
            inbound_message_id=claim.inbound_message_id, owner_token=claim.owner_token, now=NOW
        )
    pause(store)
    persisted = rows(path, "message_processing")[0]
    assert persisted["attempt_count"] == attempts
    assert persisted["state"] == "suppressed"
    assert persisted["owner_token"] is persisted["lease_expires_at"] is None
    assert not complete(store, claim)
    future = NOW + timedelta(days=100)
    assert not store.claim_generation(inbound(), now=future).acquired
    assert not store.claim_exhausted_finalization(
        inbound_message_id=claim.inbound_message_id, now=future
    ).acquired
    assert not store.mark_generation_retryable(
        inbound_message_id=claim.inbound_message_id, owner_token=claim.owner_token, now=future
    )
    with pytest.raises(GenerationRecoveryNotAvailable):
        store.load_recoverable_inbound_message(
            inbound_message_id=claim.inbound_message_id, now=future
        )
    assert rows(path, "outbound_deliveries") == []


def test_expired_lease_restart_and_new_message_never_resume(pausedb):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    pause(store, now=NOW + timedelta(seconds=31))
    reopened = SqliteConversationStore(path)
    reopened.initialize()
    for message in (inbound(), replace(inbound(), provider_message_id="after-pause")):
        assert (
            reopened.claim_generation(message, now=NOW + timedelta(days=2)).state
            is GenerationState.SUPPRESSED
        )
    assert not complete(reopened, claim, now=NOW + timedelta(days=2))
    assert reopened.list_pending_generations(now=NOW + timedelta(days=2)) == []
    assert controls(path)[0]["paused"] == 1


def test_duplicate_envelope_and_logical_message_apply_once_concurrently(pausedb):
    _, path = pausedb
    barrier = Barrier(3)

    def write(event):
        barrier.wait(timeout=5)
        pause(SqliteConversationStore(path), event)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(write, [human(), human(), identified(human(), "other-envelope")]))
    assert len(rows(path)) == 2
    assert len(rows(path, "human_pause_effects")) == 1
    assert controls(path)[0]["revision"] == 1
    before = controls(path)
    SqliteConversationStore(path).initialize()
    assert controls(path) == before
    new_message = replace(
        identified(aliased(human()), "new-event"), provider_message_id="new-human"
    )
    pause(SqliteConversationStore(path), new_message, now=NOW - timedelta(days=1))
    assert controls(path)[0]["revision"] == 2  # A unique late event remains effective.


@pytest.mark.parametrize(
    "case", ["wrong_channel", "ambiguous_channels", "missing_channel", "empty_conversation"]
)
def test_uncorrelatable_human_activity_is_only_journaled(pausedb, case):
    store, path = pausedb
    if case == "empty_conversation":
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO conversations VALUES (1, 'synthetic', 'customer', ?, ?)",
                (NOW.isoformat(), NOW.isoformat()),
            )
    else:
        first = (
            replace(inbound(), recipient_address="other-channel")
            if case == "wrong_channel"
            else inbound()
        )
        store.admit_generation(first, now=NOW)
        if case == "ambiguous_channels":
            store.admit_generation(
                replace(inbound(), provider_message_id="second", recipient_address="other-channel"),
                now=NOW,
            )
        if case == "missing_channel":
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE messages SET recipient_address = ''")
    # A matching Message alias does not override missing/contradictory channel identity.
    event = replace(
        human(),
        metadata=replace(
            human().metadata,
            message_aliases=(MessageReference("synthetic", inbound().provider_message_id),),
        ),
    )
    pause(store, event)
    assert len(rows(path)) == 1
    assert controls(path) == rows(path, "human_pause_effects") == []
    assert all(row["state"] == "retryable" for row in rows(path, "message_processing"))


def test_controlled_conversation_rejects_channel_change_without_pii(pausedb, caplog):
    store, path = pausedb
    pause(store)
    with pytest.raises(PersistenceUnavailable) as caught:
        store.record_webhook_events((replace(inbound(), recipient_address="PRIVATE-CHANNEL"),))
    assert "PRIVATE-CHANNEL" not in str(caught.value) + caplog.text
    assert rows(path, "messages") == []
    assert controls(path)[0]["channel_id"] == "studio"


@pytest.mark.parametrize("human_first", [False, True])
def test_mixed_batch_suppresses_same_conversation_in_either_order(pausedb, human_first):
    store, path = pausedb
    events = (human(), inbound()) if human_first else (inbound(), human())
    store.record_webhook_events(events)
    assert rows(path, "message_processing")[0]["state"] == "suppressed"
    assert len(rows(path)) == len(rows(path, "human_pause_effects")) == 1
    assert rows(path, "outbound_deliveries") == []


@pytest.mark.parametrize("failure", ["invalid", "effect", "commit"])
def test_batch_failure_reverts_journal_pause_and_claim_invalidation(pausedb, monkeypatch, failure):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    before = rows(path, "message_processing")
    events = (human(), replace(inbound(), provider_message_id="new-inbound"))
    if failure == "invalid":
        events += (object(),)
    elif failure == "effect":
        with sqlite3.connect(path) as connection:
            connection.execute("""CREATE TRIGGER fail_effect BEFORE INSERT ON human_pause_effects
                BEGIN SELECT RAISE(ABORT, 'PRIVATE-SQL-SENTINEL'); END""")
    else:
        original = store._connect

        @contextmanager
        def fail_commit(*args, **kwargs):
            with original(*args, **kwargs) as connection:
                connection.execute("PRAGMA defer_foreign_keys = ON")
                yield connection
                if connection.in_transaction:
                    connection.execute(
                        "INSERT INTO operational_event_aliases VALUES (-1, 'ns', 'id')"
                    )

        monkeypatch.setattr(store, "_connect", fail_commit)
    with pytest.raises((ValueError, PersistenceUnavailable)) as caught:
        store.record_webhook_events(events, now=NOW)
    assert "PRIVATE-SQL-SENTINEL" not in str(caught.value)
    assert rows(path) == controls(path) == rows(path, "human_pause_effects") == []
    assert rows(path, "message_processing") == before
    assert len(rows(path, "messages")) == 1
    monkeypatch.undo()
    assert complete(store, claim)  # The rollback preserved the original authorization.


def test_other_conversation_and_provider_continue_independently(pausedb):
    store, path = pausedb
    first = store.claim_generation(inbound(), now=NOW)
    others = [
        replace(inbound(), customer_address="another-customer", provider_message_id="other"),
        replace(inbound(), provider="another-provider"),
    ]
    other_claims = [store.claim_generation(message, now=NOW) for message in others]
    pause(store)
    assert not complete(store, first)
    assert all(complete(store, claim) for claim in other_claims)
    assert len(rows(path, "outbound_deliveries")) == 2


def test_policy_handoff_and_release_do_not_release_operational_pause(pausedb):
    store, path = pausedb
    claim, handoff = _activate(store, message=inbound(), now=NOW)
    before = rows(path, "outbound_deliveries")
    pause(store)
    assert store.list_active_handoffs() == [handoff]
    assert rows(path, "outbound_deliveries") == before
    assert controls(path)[0]["paused"] == 1
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token, now=NOW
    )
    assert controls(path)[0]["paused"] == 1
    assert (
        store.claim_generation(replace(inbound(), provider_message_id="future"), now=NOW).state
        is GenerationState.SUPPRESSED
    )
    assert (
        store.get_generation(
            provider="synthetic", provider_message_id=inbound().provider_message_id
        ).state
        is GenerationState.COMPLETED
    )


@pytest.mark.parametrize("state", [DeliveryState.PENDING, DeliveryState.UNKNOWN])
def test_already_persisted_reply_and_outbound_state_remain_unchanged(pausedb, state):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Already persisted",
        delivery_state=state,
        now=NOW,
    )
    before = rows(path, "outbound_deliveries")
    messages = rows(path, "messages")
    pause(store)
    assert rows(path, "outbound_deliveries") == before
    assert rows(path, "messages") == messages
    delivery = store.claim_next_delivery(now=NOW)
    assert (delivery is not None) == (state is DeliveryState.PENDING)
    # Pending outbound is deliberately NOT fenced until Ticket 04.


@pytest.mark.parametrize("pause_first", [False, True])
def test_pause_vs_completion_commit_race_has_two_explicit_orders(pausedb, monkeypatch, pause_first):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    entered, release, contender = Event(), Event(), Event()
    original = store._connect
    needle = "INSERT INTO human_pause_effects" if pause_first else "INSERT INTO outbound_deliveries"

    @contextmanager
    def gated(*args, **kwargs):
        with original(*args, **kwargs) as connection:

            def trace(sql):
                if needle in sql:
                    entered.set()
                    assert release.wait(timeout=5)

            connection.set_trace_callback(trace)
            yield connection

    monkeypatch.setattr(store, "_connect", gated)
    other = SqliteConversationStore(path)

    def second():
        contender.set()
        return complete(other, claim) if pause_first else pause(other)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(pause, store) if pause_first else pool.submit(complete, store, claim)
        try:
            assert entered.wait(timeout=5)
            next_result = pool.submit(second)
            assert contender.wait(timeout=5)
        finally:
            release.set()
        first_result = first.result(timeout=5)
        second_result = next_result.result(timeout=5)
    assert (second_result if pause_first else first_result) is (not pause_first)
    assert controls(path)[0]["paused"] == 1
    assert len(rows(path, "outbound_deliveries")) == (0 if pause_first else 1)


def test_revision_is_checked_even_if_paused_flag_is_cleared_outside_runtime(pausedb):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    # Fault injection: revision changes without normal suppression. There is no resume API.
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO conversation_automation_controls VALUES (1, 'studio', 0, 1, ?)",
            (NOW.isoformat(),),
        )
    assert not complete(store, claim)
    assert rows(path, "outbound_deliveries") == []


def test_journal_receipt_without_effect_is_applied_on_restart(pausedb):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    with store._connect() as connection:
        record_operational_event(connection, human(), received_at=NOW.isoformat())
    assert controls(path) == []
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert controls(path)[0]["paused"] == 1
    assert not complete(restarted, claim)
    assert len(rows(path, "human_pause_effects")) == 1


def test_purge_and_explicit_deletion_cannot_erase_pause(pausedb):
    store, path = pausedb
    store.record_webhook_events((inbound(), human()), now=NOW)
    store.purge_messages_older_than(NOW + timedelta(days=100))
    assert rows(path, "messages") == []
    assert controls(path)[0]["paused"] == 1
    with pytest.raises(PersistenceUnavailable):
        store.delete_conversation(provider="synthetic", customer_address="customer")
    assert (
        store.claim_generation(replace(inbound(), provider_message_id="after-purge"), now=NOW).state
        is GenerationState.SUPPRESSED
    )


@pytest.mark.parametrize("make_event", [edit, revoke, lifecycle])
def test_other_operational_categories_do_not_pause(pausedb, make_event):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    store.record_webhook_events((make_event(),))
    assert controls(path) == []
    assert complete(store, claim)


@pytest.mark.parametrize("interrupt", [False, True])
def test_migration_preserves_leaf_rows_and_triggers_or_rolls_back(tmp_path, monkeypatch, interrupt):
    path = tmp_path / "legacy.db"
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda config, _: original(config, "0014_operational_event_journal")
        )
        MigrationManager(path).upgrade()
    # Old runtime rows: no new-column claim path used before migration.
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO conversations VALUES (1, 'synthetic', 'customer', ?, ?)",
            (NOW.isoformat(), NOW.isoformat()),
        )
        connection.execute(
            "INSERT INTO messages (conversation_id, provider, provider_message_id, "
            "recipient_address, direction, body, created_at) "
            "VALUES (1, 'synthetic', 'message', 'studio', 'inbound', 'Synthetic', ?)",
            (NOW.isoformat(),),
        )
        connection.execute(
            "UPDATE message_processing SET state='processing', attempt_count=2, "
            "owner_token='synthetic-owner', lease_expires_at=?",
            (NOW.isoformat(),),
        )
        before = connection.execute("SELECT * FROM message_processing").fetchall()
        triggers = dict(
            connection.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
        )

    def fault(conn, cursor, statement, parameters, context, executemany):
        if "DROP TABLE message_processing" in statement:
            raise RuntimeError("Synthetic migration interruption")

    if interrupt:
        sqlalchemy_event.listen(Engine, "after_cursor_execute", fault)
    try:
        if interrupt:
            with pytest.raises(RuntimeError, match="Synthetic migration interruption"):
                MigrationManager(path).upgrade()
        else:
            MigrationManager(path).upgrade()
    finally:
        if interrupt:
            sqlalchemy_event.remove(Engine, "after_cursor_execute", fault)
    with sqlite3.connect(path) as connection:
        after = connection.execute("SELECT * FROM message_processing").fetchall()
        assert (after if interrupt else [row[:-1] for row in after]) == before
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        current = dict(
            connection.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
        )
        assert all(current[name] == sql for name, sql in triggers.items())
    if not interrupt:
        pause(SqliteConversationStore(path))
        assert rows(path, "message_processing")[0]["attempt_count"] == 2
        assert rows(path, "message_processing")[0]["state"] == "suppressed"


@pytest.mark.parametrize("pause_first", [False, True])
def test_pause_vs_claim_race_is_serialized(pausedb, monkeypatch, pause_first):
    store, path = pausedb
    store.admit_generation(inbound(), now=NOW)
    entered, release, contender = Event(), Event(), Event()
    original = store._connect
    needle = "INSERT INTO human_pause_effects" if pause_first else "automation_revision = COALESCE"

    @contextmanager
    def gated(*args, **kwargs):
        with original(*args, **kwargs) as connection:

            def trace(sql):
                if needle in sql:
                    entered.set()
                    release.wait(timeout=5)

            connection.set_trace_callback(trace)
            yield connection

    monkeypatch.setattr(store, "_connect", gated)
    other = SqliteConversationStore(path)

    def second():
        contender.set()
        return other.claim_generation(inbound(), now=NOW) if pause_first else pause(other)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = (
            pool.submit(pause, store)
            if pause_first
            else pool.submit(store.claim_generation, inbound(), now=NOW)
        )
        try:
            assert entered.wait(timeout=5)
            next_result = pool.submit(second)
            assert contender.wait(timeout=5)
        finally:
            release.set()
        first_result, second_result = first.result(timeout=5), next_result.result(timeout=5)
    claim = second_result if pause_first else first_result
    assert claim.acquired is (not pause_first)
    assert (
        store.get_generation(
            provider="synthetic", provider_message_id=inbound().provider_message_id
        ).state
        is GenerationState.SUPPRESSED
    )
    if claim.acquired:
        assert not complete(other, claim)
    assert rows(path, "outbound_deliveries") == []


def test_in_flight_outbound_keeps_its_owner_and_can_finalize_after_pause(pausedb):
    store, path = pausedb
    claim = store.claim_generation(inbound(), now=NOW)
    assert complete(store, claim)
    delivery = store.claim_next_delivery(now=NOW)
    assert store.authorize_delivery_submission(
        delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=NOW
    )
    before = rows(path, "outbound_deliveries")
    attempts = rows(path, "delivery_attempts")
    pause(store)
    assert rows(path, "outbound_deliveries") == before
    assert rows(path, "delivery_attempts") == attempts
    assert store.finalize_delivery(
        delivery_id=delivery.delivery_id,
        owner_token=delivery.owner_token,
        outcome=DeliveryState.UNKNOWN,
        safe_error_code="synthetic_unknown",
        now=NOW,
    )
    assert store.claim_next_delivery(now=NOW + timedelta(days=100)) is None
    assert rows(path, "outbound_deliveries")[0]["state"] == "unknown"


def test_raw_insert_and_claim_updates_cannot_bypass_pause(pausedb):
    store, path = pausedb
    pause(store)
    claim = store.admit_generation(inbound(), now=NOW)
    with store._connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO messages (conversation_id, provider, direction, body, "
                "created_at, in_reply_to_message_id) VALUES (1, 'synthetic', "
                "'outbound', 'Synthetic bypass', ?, ?)",
                (NOW.isoformat(), claim.inbound_message_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE message_processing SET state='processing', "
                "owner_token='bypass', lease_expires_at=?, attempt_count=1",
                (NOW.isoformat(),),
            )
    assert rows(path, "outbound_deliveries") == []


@pytest.mark.parametrize(
    "missing", ["uq_human_pause_message", "operational_pause_rejects_reply_insert"]
)
def test_readiness_requires_pause_integrity_structures(pausedb, missing):
    store, path = pausedb
    assert store.migrations_are_current()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP {'INDEX' if missing.startswith('uq_') else 'TRIGGER'} {missing}")
    assert not store.migrations_are_current()


def test_two_conversations_generate_in_parallel_and_only_paused_one_loses_reply(pausedb):
    store, path = pausedb
    store.record_webhook_events((inbound(),))
    generator_a, generator_b = _BlockingGenerator(), _BlockingGenerator()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runner(store, generator_a).run_once)
        try:
            assert generator_a.entered.wait(timeout=5)
            store.record_webhook_events(
                (
                    replace(
                        inbound(), provider_message_id="parallel-b", customer_address="customer-b"
                    ),
                )
            )
            second = pool.submit(runner(SqliteConversationStore(path), generator_b).run_once)
            assert generator_b.entered.wait(timeout=5)
            # Both generators are live; only A's exact identity receives the echo.
            pause(SqliteConversationStore(path), now=None)
            generator_b.release.set()
            completed_b = second.result(timeout=5)
            assert completed_b is not None
            assert completed_b.state is GenerationState.COMPLETED
            assert not first.done()
            assert len(rows(path, "outbound_deliveries")) == 1
            generator_a.release.set()
            assert first.result(timeout=5) is None
        finally:
            generator_a.release.set()
            generator_b.release.set()
    assert (
        store.get_generation(
            provider="synthetic", provider_message_id=inbound().provider_message_id
        ).state
        is GenerationState.SUPPRESSED
    )
    assert len(controls(path)) == 1
    assert len(rows(path, "outbound_deliveries")) == 1
