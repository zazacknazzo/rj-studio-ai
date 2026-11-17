"""Ticket 09 offline lifecycle contract, atomicity and concurrency on real SQLite."""

import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import Engine
from test_async_ingress import _BlockingGenerator
from test_generation_pause import complete, runner
from test_operational_event_journal import rows
from test_telnyx_authentication import NOW, PHONE, PRIVATE_TEXT, WABA, lifecycle, signed
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_delivery_status import accept, claim_delivery, pending, status_wire
from test_telnyx_messages import CUSTOMER, TIME, receive, wire
from test_telnyx_messages import ingress as ingress

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationRecoveryNotAvailable,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import InvalidWebhookPayload, InvalidWebhookSignature
from rj_studio_ai.providers.telnyx_messages import TelnyxMessageAdapter
from rj_studio_ai.webhook_ingress import receive_telnyx_messages


def account(transition="ACCOUNT_OFFBOARDED", *, event_id="lifecycle-1", occurred=TIME):
    result = lifecycle()
    result["data"].update(id=event_id, occurred_at=occurred.isoformat())
    result["data"]["payload"]["event"] = transition
    return result


def inbound(message_id="new-inbound"):
    return InboundMessage("telnyx", message_id, CUSTOMER, PHONE, "Synthetic content")


def state(path):
    return rows(path, "channel_lifecycle")[0]


@pytest.mark.parametrize(
    "transition,expected,reason",
    [
        ("ACCOUNT_OFFBOARDED", "blocked", "offboarded"),
        ("PARTNER_REMOVED", "blocked", "disconnected"),
        ("ACCOUNT_RECONNECTED", "verification_required", "reconnected"),
    ],
)
def test_contract_commit_before_ack_restart_and_duplicate(
    ingress, private_key, monkeypatch, transition, expected, reason
):
    adapter, store, path = ingress
    original = adapter.acknowledge

    def ack():
        assert state(path)["state"] == expected
        assert len(rows(path, "channel_lifecycle_effects")) == 1
        return original()

    monkeypatch.setattr(adapter, "acknowledge", ack)
    payload = account(transition)
    assert receive(ingress, private_key, payload).status_code == 204
    observation = rows(path)[0]
    assert observation["scope_kind"] == "account"
    assert observation["scope_id"] == WABA
    assert observation["provider_message_id"] is observation["customer_address"] is None
    assert observation["reason"] == reason
    before = state(path)
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert receive((adapter, restarted, path), private_key, payload).status_code == 204
    assert state(path) == before
    assert len(rows(path)) == 1
    assert rows(path, "conversations") == []
    assert rows(path, "conversation_automation_controls") == []
    assert restarted.claim_generation(inbound(), now=TIME).state is GenerationState.SUPPRESSED
    assert restarted.claim_next_delivery(now=TIME) is None


@pytest.mark.parametrize("bound", [False, True])
def test_absence_of_verification_is_never_active(tmp_path, settings, private_key, bound):
    path = tmp_path / "unverified.db"
    store = SqliteConversationStore(path)
    store.initialize()
    adapter = TelnyxMessageAdapter(settings, clock=lambda: NOW)
    if bound:
        receive((adapter, store, path), private_key, wire())
        assert state(path)["state"] == "verification_required"
    assert store.claim_generation(inbound(), now=TIME).state is GenerationState.SUPPRESSED
    assert runner(store).run_once() is None
    assert rows(path, "outbound_deliveries") == []


@pytest.mark.parametrize("change", ["waba", "record", "missing", "unknown", "time", "event_id"])
def test_bad_contract_no_ack_no_effect(ingress, private_key, monkeypatch, change):
    adapter, _, path = ingress
    monkeypatch.setattr(adapter, "acknowledge", lambda: pytest.fail("unexpected ACK"))
    payload = account()
    if change == "waba":
        payload["data"]["payload"]["waba_id"] = "other-waba"
    elif change == "record":
        payload["data"]["payload"]["record_type"] = "message"
    elif change == "missing":
        del payload["data"]["payload"]["waba_id"]
    elif change == "unknown":
        payload["data"]["payload"]["event"] = PRIVATE_TEXT
    elif change == "time":
        payload["data"]["occurred_at"] = "2026-01-01T01:01:01"
    else:
        del payload["data"]["id"]
    with pytest.raises(InvalidWebhookPayload) as caught:
        receive(ingress, private_key, payload)
    assert PRIVATE_TEXT not in str(caught.value)
    assert rows(path) == []
    assert state(path)["revision"] == 0


def test_bad_signature_precedes_json_and_lifecycle(ingress, private_key, monkeypatch):
    adapter, store, path = ingress
    monkeypatch.setattr(adapter, "acknowledge", lambda: pytest.fail("unexpected ACK"))
    request = signed(private_key, account())
    with pytest.raises(InvalidWebhookSignature):
        receive_telnyx_messages(
            (replace(request, body=b"not-json"),),
            adapter=adapter,
            store=store,
            deadline=ExecutionDeadline.start(),
        )
    assert rows(path) == []


@pytest.mark.parametrize("transition", ["PARTNER_REMOVED", "ACCOUNT_RECONNECTED"])
def test_conflicting_replay_rolls_back_whole_batch(ingress, private_key, transition):
    receive(ingress, private_key, account())
    before = state(ingress[2])
    with pytest.raises(ValueError, match="Conflicting"):
        receive(ingress, private_key, account(event_id="new"), account(transition))
    assert len(rows(ingress[2])) == 1
    assert state(ingress[2]) == before


@pytest.mark.parametrize(
    "first,second",
    [
        ("ACCOUNT_OFFBOARDED", "ACCOUNT_RECONNECTED"),
        ("ACCOUNT_RECONNECTED", "ACCOUNT_OFFBOARDED"),
        ("PARTNER_REMOVED", "ACCOUNT_RECONNECTED"),
    ],
)
@pytest.mark.parametrize("days", [-100, 0, 100])
def test_reordering_and_wrong_clock_never_enable(ingress, private_key, first, second, days):
    receive(ingress, private_key, account(first, event_id="z-first"))
    second_event = account(second, event_id="a-last", occurred=TIME + timedelta(days=days))
    receive(ingress, private_key, second_event, now=TIME - timedelta(days=1))
    expected = "verification_required" if second == "ACCOUNT_RECONNECTED" else "blocked"
    assert state(ingress[2])["state"] == expected
    assert state(ingress[2])["revision"] == 2
    # Replay of an older envelope cannot change the last applied local observation.
    receive(ingress, private_key, account(first, event_id="z-first"))
    assert state(ingress[2])["state"] == expected
    assert not ingress[1].claim_generation(inbound(), now=TIME).acquired


@pytest.mark.parametrize("claimed", [False, True])
def test_pending_or_owned_generation_suppressed_without_resetting_attempts(
    ingress, private_key, claimed
):
    _, store, path = ingress
    claim = (store.claim_generation if claimed else store.admit_generation)(inbound(), now=TIME)
    receive(ingress, private_key, account())
    processing = rows(path, "message_processing")[0]
    assert processing["state"] == "suppressed"
    assert processing["attempt_count"] == int(claimed)
    assert processing["owner_token"] is None
    assert not complete(store, replace(claim, owner_token=claim.owner_token or "stale"), now=TIME)
    assert not store.mark_generation_retryable(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token or "stale",
        now=TIME,
    )
    assert not store.claim_exhausted_finalization(
        inbound_message_id=claim.inbound_message_id, now=TIME
    ).acquired
    with pytest.raises(GenerationRecoveryNotAvailable):
        store.load_recoverable_inbound_message(inbound_message_id=claim.inbound_message_id)
    assert runner(store).run_once() is None


def test_block_during_llm_has_no_writer_lock_or_reply(ingress, private_key, caplog):
    adapter, store, path = ingress
    store.admit_generation(inbound())
    generator = _BlockingGenerator()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner(store, generator).run_once)
        try:
            assert generator.entered.wait(5)
            receive((adapter, SqliteConversationStore(path), path), private_key, account())
        finally:
            generator.release.set()
        assert future.result(5) is None
    assert len(rows(path, "messages")) == 1
    assert rows(path, "outbound_deliveries") == []
    assert PRIVATE_TEXT not in caplog.text


@pytest.mark.parametrize("owned", [False, True])
def test_block_cancels_only_unsubmitted_delivery(ingress, private_key, owned):
    _, store, path = ingress
    pending(store)
    claim = store.claim_next_delivery(now=TIME) if owned else None
    before = rows(path, "messages")
    receive(ingress, private_key, account())
    delivery = rows(path, "outbound_deliveries")[0]
    assert delivery["state"] == "cancelled"
    assert delivery["attempt_count"] == int(owned)
    assert rows(path, "messages") == before
    if claim:
        assert not store.authorize_delivery_submission(
            delivery_id=claim.delivery_id, owner_token=claim.owner_token, now=TIME
        )
        assert (
            rows(path, "delivery_attempts")[0]["safe_error_code"] == "channel_lifecycle_cancelled"
        )
    assert store.claim_next_delivery(now=TIME + timedelta(days=10)) is None


@pytest.mark.parametrize("outcome", ["accepted", "retryable", "unknown"])
@pytest.mark.parametrize("exhausted", [False, True])
def test_previously_authorized_result_is_preserved_and_never_resends(
    ingress, private_key, outcome, exhausted
):
    _, store, path = ingress
    pending(store)
    claim = claim_delivery(store)
    before = rows(path, "outbound_deliveries")
    receive(ingress, private_key, account())
    assert rows(path, "outbound_deliveries") == before
    assert not store.authorize_delivery_submission(
        delivery_id=claim.delivery_id, owner_token=claim.owner_token, now=TIME
    )
    kwargs = (
        {"provider_message_id": "accepted-message"}
        if outcome == "accepted"
        else {"safe_error_code": "synthetic_result"}
    )
    if outcome == "retryable":
        kwargs.update(retry_at=TIME + timedelta(seconds=1), retry_exhausted=exhausted)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState(outcome),
        now=TIME,
        **kwargs,
    )
    assert rows(path, "outbound_deliveries")[0]["state"] == (
        "cancelled" if outcome == "retryable" else outcome
    )
    assert rows(path, "delivery_attempts")[0]["outcome"] == outcome
    receive(ingress, private_key, account("ACCOUNT_RECONNECTED", event_id="reconnect"))
    assert store.claim_next_delivery(now=TIME + timedelta(days=2)) is None


@pytest.mark.parametrize("delivery_state", [DeliveryState.UNKNOWN, DeliveryState.ACCEPTED_LEGACY])
def test_legacy_authorization_and_handoff_release_cannot_bypass(
    ingress, private_key, delivery_state
):
    from rj_studio_ai.handoff import HandoffReason

    _, store, path = ingress
    claim = store.claim_generation(inbound(), now=TIME)
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Synthetic handoff",
        delivery_state=delivery_state,
        handoff_reason=HandoffReason.HUMAN_REVIEW_REQUIRED,
        now=TIME,
    )
    delivery = rows(path, "outbound_deliveries")[0]
    assert store.authorize_legacy_reply(delivery_id=delivery["id"])
    receive(ingress, private_key, account())
    handoff = rows(path, "conversation_handoffs")[0]
    assert store.release_handoff(
        conversation_id=handoff["conversation_id"], owner_token=handoff["owner_token"], now=TIME
    )
    assert not store.authorize_legacy_reply(delivery_id=delivery["id"])
    assert not store.claim_generation(inbound("after-release"), now=TIME).acquired


def test_pause_resume_independent_of_lifecycle(ingress, private_key):
    _, store, path = ingress
    receive(ingress, private_key, wire("echo"))
    control = rows(path, "conversation_automation_controls")[0]
    opaque = rows(path, "conversation_operation_ids")[0]["opaque_id"]
    receive(ingress, private_key, account())
    store.change_automation(opaque, "resume", "a" * 32, control["revision"], "operator", now=TIME)
    assert rows(path, "conversation_automation_controls")[0]["paused"] == 0
    receive(
        ingress,
        private_key,
        wire(source=NOW + 2, occurred=NOW + 3),
        now=TIME + timedelta(seconds=4),
    )
    assert rows(path, "message_processing")[0]["state"] == "suppressed"
    assert state(path)["state"] == "blocked"


@pytest.mark.parametrize("phase", ["statement", "commit"])
def test_sqlite_failure_rolls_back_observation_effect_and_cancellation(
    ingress, private_key, monkeypatch, phase, caplog
):
    adapter, store, path = ingress
    pending(store)
    before = rows(path, "outbound_deliveries")
    channel_before = state(path)
    monkeypatch.setattr(adapter, "acknowledge", lambda: pytest.fail("unexpected ACK"))
    if phase == "statement":
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TRIGGER synthetic_failure BEFORE INSERT ON "
                "channel_lifecycle_effects BEGIN SELECT RAISE(ABORT, 'PRIVATE sentinel'); END"
            )
    else:
        original = store._connect

        @contextmanager
        def broken(*args, **kwargs):
            with original(*args, **kwargs) as connection:
                yield connection
                raise sqlite3.OperationalError("PRIVATE sentinel")

        monkeypatch.setattr(store, "_connect", broken)
    with pytest.raises(PersistenceUnavailable) as caught:
        receive(ingress, private_key, account())
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value)) + caplog.text
    assert rows(path) == rows(path, "channel_lifecycle_effects") == []
    assert state(path) == channel_before
    assert rows(path, "outbound_deliveries") == before


def test_lost_ack_restart_and_replay(ingress, private_key, monkeypatch):
    adapter, _, path = ingress
    original = adapter.acknowledge

    def lost():
        raise ConnectionError("synthetic lost ACK")

    monkeypatch.setattr(adapter, "acknowledge", lost)
    with pytest.raises(ConnectionError):
        receive(ingress, private_key, account())
    monkeypatch.setattr(adapter, "acknowledge", original)
    store = SqliteConversationStore(path)
    store.initialize()
    assert receive((adapter, store, path), private_key, account()).status_code == 204
    assert state(path)["revision"] == 1


@pytest.mark.parametrize("competitor", ["claim", "complete", "authorize", "callback", "duplicate"])
def test_writer_concurrency_has_atomic_outcomes(ingress, private_key, competitor):
    adapter, store, path = ingress
    generation = store.claim_generation(inbound(), now=TIME) if competitor == "complete" else None
    if competitor in ("authorize", "callback"):
        pending(store)
        delivery = store.claim_next_delivery(now=TIME)
        if competitor == "callback":
            assert store.authorize_delivery_submission(
                delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=TIME
            )
            accept(store, delivery)
    barrier = Barrier(2)

    def block():
        barrier.wait(5)
        return receive((adapter, SqliteConversationStore(path), path), private_key, account())

    def other():
        peer = SqliteConversationStore(path)
        barrier.wait(5)
        if competitor == "claim":
            return peer.claim_generation(inbound(), now=TIME)
        if competitor == "complete":
            return complete(peer, generation, now=TIME)
        if competitor == "authorize":
            return peer.authorize_delivery_submission(
                delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=TIME
            )
        return receive(
            (adapter, peer, path),
            private_key,
            status_wire() if competitor == "callback" else account(),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(block), pool.submit(other)
        a.result(10)
        result = b.result(10)
    assert state(path)["state"] == "blocked"
    if competitor == "claim":
        assert rows(path, "message_processing")[0]["state"] == "suppressed"
    elif competitor == "complete":
        assert len(rows(path, "outbound_deliveries")) == int(result)
        if result:
            assert rows(path, "outbound_deliveries")[0]["state"] == "cancelled"
    elif competitor == "authorize":
        assert rows(path, "outbound_deliveries")[0]["state"] == (
            "sending" if result else "cancelled"
        )
    elif competitor == "callback":
        assert rows(path, "outbound_deliveries")[0]["state"] == "delivered"
    else:
        assert state(path)["revision"] == 1
    assert store.claim_next_delivery(now=TIME + timedelta(days=1)) is None


def test_lock_deadline_no_ack_then_retry(ingress, private_key):
    with sqlite3.connect(ingress[2]) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(PersistenceUnavailable):
            receive(
                ingress,
                private_key,
                account(),
                deadline=ExecutionDeadline.start(total_seconds=0.03, finalization_margin_seconds=0),
            )
    assert rows(ingress[2]) == []
    assert receive(ingress, private_key, account()).status_code == 204


@pytest.mark.parametrize("interrupt", [False, True])
def test_migration_from_0019_is_atomic_and_preserves_history(tmp_path, monkeypatch, interrupt):
    path = tmp_path / "migration.db"
    manager = MigrationManager(path)
    original = command.upgrade
    monkeypatch.setattr(
        command, "upgrade", lambda config, _: original(config, "0019_scoped_delivery_status")
    )
    manager.upgrade()
    # Before lifecycle, synthetic Telnyx work can be pending. Preserve its bodies and attempts.
    store = SqliteConversationStore(path)
    # The pre-0020 database is seeded using its historical SQL fixture, not current gated methods.
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO conversations VALUES (1,'telnyx',?,'2000','2000')", (CUSTOMER,)
        )
        connection.execute(
            "INSERT INTO messages(conversation_id,provider,provider_message_id,"
            "recipient_address,direction,body,created_at) "
            "VALUES(1,'telnyx','historical',?,'inbound',"
            "'Synthetic history','2000')",
            (PHONE,),
        )
    before = rows(path, "messages")
    backup = tmp_path / "baseline-backup.db"
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    monkeypatch.setattr(command, "upgrade", original)

    def fail(conn, cursor, statement, parameters, context, many):
        if "CREATE TRIGGER channel_rejects_submission" in statement:
            raise RuntimeError("synthetic migration failure")

    if interrupt:
        sqlalchemy_event.listen(Engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError, match="synthetic migration"):
                manager.upgrade()
        finally:
            sqlalchemy_event.remove(Engine, "before_cursor_execute", fail)
        with sqlite3.connect(path) as connection:
            assert (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "0019_scoped_delivery_status"
            )
            assert not connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='channel_lifecycle'"
            ).fetchone()
        assert rows(path, "message_processing")[0]["state"] == "retryable"
    store.initialize()
    assert manager.is_current()
    assert rows(path, "messages") == before
    assert rows(path, "message_processing")[0]["state"] == "suppressed"
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    restored = tmp_path / "restored-0019.db"
    with sqlite3.connect(backup) as source, sqlite3.connect(restored) as destination:
        source.backup(destination)
    restored_store = SqliteConversationStore(restored)
    restored_store.initialize()
    assert restored_store.migrations_are_current()
    assert rows(restored, "messages") == before
    assert rows(restored, "message_processing")[0]["state"] == "suppressed"


def test_block_between_claim_and_llm_never_calls_generator(ingress, private_key, monkeypatch):
    from rj_studio_ai.application import RetryableWebhookError
    from rj_studio_ai.generation import FixedReplyGenerator

    _, store, path = ingress
    message = inbound()
    claim = store.claim_generation(message)
    generator = FixedReplyGenerator("Synthetic reply")
    process = runner(store, generator).responder
    original = process._build_context

    def block(*args, **kwargs):
        context = original(*args, **kwargs)
        receive(ingress, private_key, account())
        return context

    monkeypatch.setattr(process, "_build_context", block)
    monkeypatch.setattr(type(generator), "generate", lambda *a, **k: pytest.fail("LLM called"))
    with pytest.raises(RetryableWebhookError, match="Channel"):
        process.process_persisted(message, preclaimed=claim)
    assert rows(path, "outbound_deliveries") == []


@pytest.mark.parametrize("kind", ["text", "echo", "status"])
@pytest.mark.parametrize("lifecycle_first", [False, True])
def test_event_identity_cannot_cross_message_and_account_scopes(
    ingress, private_key, kind, lifecycle_first
):
    message = status_wire(event_id="shared") if kind == "status" else wire(kind, event_id="shared")
    change = account(event_id="shared")
    first, second = (change, message) if lifecycle_first else (message, change)
    receive(ingress, private_key, first)
    before = state(ingress[2])
    with pytest.raises(ValueError, match="Conflicting"):
        receive(ingress, private_key, second)
    assert state(ingress[2]) == before


def test_maintenance_and_restart_preserve_account_block(ingress, private_key):
    adapter, store, path = ingress
    pending(store)
    receive(ingress, private_key, account())
    before = state(path)
    journal = rows(path)
    store.purge_messages_older_than(TIME + timedelta(days=1))
    store.delete_conversation(provider="telnyx", customer_address=CUSTOMER)
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert state(path) == before
    assert rows(path) == journal
    assert len(rows(path, "channel_lifecycle_effects")) == 1
    receive((adapter, restarted, path), private_key, wire())
    assert rows(path, "message_processing")[0]["state"] == "suppressed"


@pytest.mark.parametrize("operation", ["reactivate", "delete", "rebind", "delete_effect"])
def test_no_sql_shortcut_can_release_or_erase_channel(ingress, private_key, operation):
    receive(ingress, private_key, account())
    sql = {
        "reactivate": "UPDATE channel_lifecycle SET state='active',last_event_record_id=NULL",
        "delete": "DELETE FROM channel_lifecycle",
        "rebind": "UPDATE channel_lifecycle SET waba_id='another-account'",
        "delete_effect": "DELETE FROM channel_lifecycle_effects",
    }[operation]
    with sqlite3.connect(ingress[2]) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(sql)
    assert state(ingress[2])["state"] == "blocked"


def test_expired_authorized_delivery_becomes_unknown_never_retry(ingress, private_key):
    _, store, path = ingress
    pending(store)
    claim_delivery(store)
    receive(ingress, private_key, account())
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert restarted.claim_next_delivery(now=TIME + timedelta(days=1)) is None
    assert rows(path, "outbound_deliveries")[0]["state"] == "unknown"
    assert rows(path, "delivery_attempts")[0]["outcome"] == "unknown"


@pytest.mark.parametrize("kind", ["offboard", "reconnect"])
def test_restored_backup_retains_block_and_replay(ingress, private_key, tmp_path, kind):
    adapter, _, path = ingress
    payload = account("ACCOUNT_OFFBOARDED" if kind == "offboard" else "ACCOUNT_RECONNECTED")
    receive(ingress, private_key, payload)
    backup = tmp_path / "restored.db"
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    store = SqliteConversationStore(backup)
    store.initialize()
    before = state(backup)
    receive((adapter, store, backup), private_key, payload)
    assert state(backup) == before
    assert not store.claim_generation(inbound(), now=TIME).acquired


@pytest.mark.parametrize(
    "object_name,kind",
    [
        ("eligible_telnyx_channels", "VIEW"),
        ("channel_rejects_submission", "TRIGGER"),
        ("channel_lifecycle_fences_update", "TRIGGER"),
    ],
)
def test_schema_damage_fails_local_readiness(ingress, object_name, kind):
    _, store, path = ingress
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP {kind} {object_name}")
    assert not store.migrations_are_current()


@pytest.mark.parametrize("transition", ["ACCOUNT_OFFBOARDED", "ACCOUNT_RECONNECTED"])
def test_sql_replace_cannot_bypass_immutable_binding(ingress, private_key, transition):
    receive(ingress, private_key, account(transition))
    before = state(ingress[2])
    with sqlite3.connect(ingress[2]) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="already exists"):
            connection.execute(
                "INSERT OR REPLACE INTO channel_lifecycle "
                "(provider,waba_id,channel_id,organization_id,profile_id,state,revision,"
                "updated_at,verification_evidence) VALUES "
                "('telnyx','another-waba','+15555550109','org','profile','active',0,'2000','fake')"
            )
    assert state(ingress[2]) == before
