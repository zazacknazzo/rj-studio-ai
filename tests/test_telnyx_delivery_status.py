"""Ticket 08: signed synthetic outbound envelopes through real SQLite, never live."""

import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from itertools import permutations
from threading import Barrier

import pytest
from alembic import command
from test_operational_event_journal import rows
from test_telnyx_authentication import NOW, ORG, PHONE, PRIVATE_TEXT, PROFILE, message, signed
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import CUSTOMER, TIME, receive, wire
from test_telnyx_messages import ingress as ingress

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import DeliveryStatusReceived, InboundMessage
from rj_studio_ai.maintenance import main as maintenance_main
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import InvalidWebhookPayload, InvalidWebhookSignature
from rj_studio_ai.webhook_ingress import receive_telnyx_messages

MESSAGE_ID = "40385f64-5717-4562-b3fc-2c963f66afa6"


def status_wire(status="delivered", *, event=None, message_id=MESSAGE_ID, event_id=None):
    result = message(event or ("message.read" if status == "read" else "message.finalized"))
    data = result["data"]
    data["id"] = event_id or "event-status-" + status
    data["occurred_at"] = TIME.isoformat()
    payload = data["payload"]
    payload.update(
        id=message_id,
        to=[{"phone_number": CUSTOMER, "status": status, "carrier": "synthetic"}],
        cc=[],
        errors=[],
        text=PRIVATE_TEXT,
        body={"foreign_id": "wamid.shared", "text": PRIVATE_TEXT},
    )
    return result


def pending(store, *, customer=CUSTOMER, channel=PHONE, provider="telnyx", message_id="inbound"):
    inbound = InboundMessage(provider, message_id, customer, channel, "Synthetic inbound")
    claim = store.claim_generation(inbound, now=TIME)
    assert claim.acquired
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Synthetic reply",
        delivery_state=DeliveryState.PENDING,
        now=TIME,
    )
    return claim.inbound_message_id


def claim_delivery(store):
    claim = store.claim_next_delivery(now=TIME)
    assert claim is not None
    assert store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        now=TIME,
    )
    return claim


def accept(store, claim=None, *, message_id=MESSAGE_ID):
    claim = claim or claim_delivery(store)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id=message_id,
        now=TIME,
    )
    return store.get_delivery(claim.delivery_id)


@pytest.mark.parametrize(
    "event,status,canonical",
    [
        ("message.sent", "sent", "sent"),
        ("message.sent", "queued", "unknown"),
        ("message.sent", "sending", "unknown"),
        *[("message.finalized", s, s) for s in ("sent", "delivered", "read")],
        *[
            ("message.finalized", s, "failed")
            for s in ("sending_failed", "delivery_failed", "failed")
        ],
        *[
            ("message.finalized", s, "unknown")
            for s in ("queued", "sending", "delivery_unconfirmed", "expired")
        ],
        ("message.read", "read", "read"),
    ],
)
def test_official_shape_minimal_evidence_and_ack(
    ingress, private_key, monkeypatch, event, status, canonical
):
    adapter, _, path = ingress
    payload = status_wire(status, event=event)
    payload["data"]["payload"]["errors"] = [{"code": PRIVATE_TEXT, "detail": PRIVATE_TEXT}]
    parsed = adapter.receive(signed(private_key, payload)).events[0]
    assert isinstance(parsed, DeliveryStatusReceived)
    assert parsed.status.value == canonical
    assert parsed.provider_message_id == MESSAGE_ID
    assert parsed.metadata.event_id != MESSAGE_ID
    assert parsed.evidence.account_id == ORG
    assert parsed.evidence.profile_id == PROFILE
    assert parsed.evidence.recipient_status == status
    assert PRIVATE_TEXT not in repr(parsed)
    original = adapter.acknowledge

    def ack():
        assert len(rows(path, "delivery_status_events")) == 1
        return original()

    monkeypatch.setattr(adapter, "acknowledge", ack)
    assert receive(ingress, private_key, payload).status_code == 204
    for table in (
        "messages",
        "conversations",
        "message_processing",
        "outbound_deliveries",
        "delivery_attempts",
        "pending_delivery_statuses",
    ):
        assert rows(path, table) == []
    assert PRIVATE_TEXT not in str(rows(path, "delivery_status_events"))


def test_invalid_signature_precedes_status_parsing(ingress, private_key):
    adapter, _, path = ingress
    request = signed(private_key, status_wire())
    with pytest.raises(InvalidWebhookSignature):
        receive_telnyx_messages(
            (replace(request, body=request.body + b" "),),
            adapter=adapter,
            store=ingress[1],
            deadline=ExecutionDeadline.start(),
            now=TIME,
        )
    assert rows(path, "delivery_status_events") == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("to", CUSTOMER),
        ("to", []),
        ("to", [None]),
        ("to", [{"phone_number": CUSTOMER, "status": "accepted"}]),
        ("to", [{"phone_number": CUSTOMER, "status": "future"}]),
        ("to", [{"phone_number": CUSTOMER, "status": []}]),
        ("to", [{"phone_number": "bsuid:opaque", "status": "read"}]),
        ("to", [{"phone_number": PHONE, "status": "read"}]),
        ("to", [{"phone_number": CUSTOMER, "status": "read"}] * 2),
        ("cc", [{"phone_number": CUSTOMER}]),
        ("from", {"phone_number": "+15555550109"}),
        ("organization_id", "other"),
        ("messaging_profile_id", "other"),
        ("waba_id", "other"),
        ("direction", "inbound"),
        ("type", "SMS"),
        ("origin", "whatsapp_business_app"),
        ("id", ""),
    ],
)
def test_bad_scope_or_shape_has_no_ack(ingress, private_key, field, value):
    payload = status_wire()
    payload["data"]["payload"][field] = value
    with pytest.raises(InvalidWebhookPayload):
        receive(ingress, private_key, payload)
    assert rows(ingress[2], "delivery_status_events") == []


@pytest.mark.parametrize(
    "event,status",
    [("message.sent", "delivered"), ("message.read", "sent"), ("message.read", "failed")],
)
def test_event_type_is_not_a_status_fallback(ingress, private_key, event, status):
    with pytest.raises(InvalidWebhookPayload):
        receive(ingress, private_key, status_wire(status, event=event))


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize(
    "statuses,expected,conflict",
    [
        (["sent"], "sent", 0),
        (["delivered", "sent"], "delivered", 0),
        (["read", "delivered", "sent"], "read", 0),
        (["failed", "sent"], "failed", 0),
        (["delivery_unconfirmed"], "accepted", 0),
        *[(list(order), "read", 1) for order in permutations(("read", "failed", "sent"))],
        (["failed", "delivered"], "delivered", 1),
        (["delivered", "failed"], "delivered", 1),
    ],
)
def test_early_late_order_restart_replay(ingress, private_key, early, statuses, expected, conflict):
    adapter, store, path = ingress
    inbound_id = pending(store)
    if not early:
        accept(store)
    for status in statuses:
        receive(ingress, private_key, status_wire(status))
    store = SqliteConversationStore(path)
    store.initialize()
    if early:
        assert rows(path, "outbound_deliveries")[0]["state"] == "pending"
        accept(store)
    reopened = SqliteConversationStore(path)
    reopened.initialize()
    for status in reversed(statuses):
        receive((adapter, reopened, path), private_key, status_wire(status))
    delivery = reopened.get_delivery_for_inbound(inbound_id)
    assert delivery.state.value == expected
    assert rows(path, "outbound_deliveries")[0]["status_conflict"] == conflict
    assert len(rows(path, "delivery_status_events")) == len(set(statuses))
    assert {r["delivery_id"] for r in rows(path, "delivery_status_events")} == {
        delivery.delivery_id
    }
    assert reopened.claim_next_delivery(now=TIME + timedelta(days=1)) is None
    assert len(rows(path, "delivery_attempts")) == 1


@pytest.mark.parametrize("change", ["status", "recipient", "message", "time", "profile", "account"])
def test_conflicting_same_event_is_rejected(ingress, private_key, settings, change):
    from rj_studio_ai.providers.telnyx_messages import TelnyxMessageAdapter

    original = status_wire(event_id="same-event")
    receive(ingress, private_key, original)
    changed = status_wire(event_id="same-event")
    data, payload = changed["data"], changed["data"]["payload"]
    if change == "status":
        payload["to"][0]["status"] = "read"
    elif change == "recipient":
        payload["to"][0]["phone_number"] = "+15555550109"
    elif change == "message":
        payload["id"] = "other-message"
    elif change == "time":
        data["occurred_at"] = (TIME - timedelta(seconds=1)).isoformat()
    else:
        attr, field = (
            ("telnyx_messaging_profile_id", "messaging_profile_id")
            if change == "profile"
            else ("telnyx_organization_id", "organization_id")
        )
        setattr(settings, attr, "changed")
        payload[field] = "changed"
        ingress = (TelnyxMessageAdapter(settings, clock=lambda: NOW), *ingress[1:])
    with pytest.raises(ValueError, match="Conflicting"):
        receive(ingress, private_key, changed)
    assert len(rows(ingress[2], "delivery_status_events")) == 1


@pytest.mark.parametrize("early", [False, True])
@pytest.mark.parametrize("mismatch", ["channel", "recipient"])
def test_outbox_scope_mismatch_never_correlates(ingress, private_key, early, mismatch):
    _, store, path = ingress
    pending(
        store,
        **({"channel": "+15555550109"} if mismatch == "channel" else {"customer": "+15555550109"}),
    )
    if early:
        receive(ingress, private_key, status_wire())
        claim = claim_delivery(store)
        with pytest.raises(ValueError, match="scope mismatch"):
            accept(store, claim)
        assert rows(path, "outbound_deliveries")[0]["state"] == "sending"
        assert rows(path, "outbound_deliveries")[0]["provider_message_id"] is None
        assert rows(path, "delivery_attempts")[0]["outcome"] == "started"
        assert rows(path, "delivery_status_events")[0]["delivery_id"] is None
    else:
        accept(store)
        with pytest.raises(ValueError, match="scope mismatch"):
            receive(ingress, private_key, status_wire())
        assert rows(path, "outbound_deliveries")[0]["state"] == "accepted"
        assert rows(path, "delivery_status_events") == []


def test_same_message_different_recipient_rejected_before_acceptance(ingress, private_key):
    receive(ingress, private_key, status_wire())
    other = status_wire("read")
    other["data"]["payload"]["to"][0]["phone_number"] = "+15555550109"
    with pytest.raises(ValueError, match="Message scope"):
        receive(ingress, private_key, other)
    assert len(rows(ingress[2], "delivery_status_events")) == 1


def test_provider_namespace_and_shared_meta_alias_never_join(ingress, private_key):
    _, store, path = ingress
    pending(store, provider="meta")
    accept(store)
    receive(ingress, private_key, status_wire())
    assert rows(path, "outbound_deliveries")[0]["state"] == "accepted"
    assert rows(path, "delivery_status_events")[0]["delivery_id"] is None
    echo = wire("echo", message_id="human-message")
    echo["data"]["payload"]["body"]["foreign_id"] = "wamid.shared"
    receive(ingress, private_key, echo)
    receive(ingress, private_key, status_wire("read", message_id="other-telnyx-message"))
    assert len(rows(path, "delivery_status_events")) == 2
    assert rows(path, "outbound_deliveries")[0]["state"] == "accepted"


@pytest.mark.parametrize("first_status", [False, True])
@pytest.mark.parametrize("kind", ["echo", "text"])
def test_human_or_inbound_identity_cannot_be_ai_status(ingress, private_key, first_status, kind):
    observation, status = wire(kind, message_id=MESSAGE_ID), status_wire()
    first, second = (status, observation) if first_status else (observation, status)
    receive(ingress, private_key, first)
    with pytest.raises(ValueError, match="Conflicting"):
        receive(ingress, private_key, second)
    assert rows(ingress[2], "outbound_deliveries") == []


def test_event_id_shared_across_event_kinds_is_rejected(ingress, private_key):
    receive(ingress, private_key, wire("echo", event_id="same"))
    with pytest.raises(ValueError, match="Conflicting"):
        receive(ingress, private_key, status_wire(event_id="same"))


@pytest.mark.parametrize("state", ["unknown", "cancelled"])
def test_local_terminal_states_are_not_revived_by_callbacks(ingress, private_key, state):
    _, store, path = ingress
    pending(store)
    if state == "unknown":
        claim = claim_delivery(store)
        assert store.finalize_delivery(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            outcome=DeliveryState.UNKNOWN,
            safe_error_code="provider_outcome_unknown",
            now=TIME,
        )
    else:
        receive(ingress, private_key, wire("echo"))
    receive(ingress, private_key, status_wire("read"), status_wire("failed"))
    assert rows(path, "outbound_deliveries")[0]["state"] == state
    assert store.claim_next_delivery(now=TIME + timedelta(days=1)) is None
    assert all(r["delivery_id"] is None for r in rows(path, "delivery_status_events"))


def test_conflict_is_visible_and_blocks_next_generation_and_resume(ingress, private_key, capsys):
    _, store, path = ingress
    inbound_id = pending(store)
    accept(store)
    receive(ingress, private_key, status_wire("read"), status_wire("failed"))
    assert maintenance_main(["--database-path", str(path), "list-blocked-deliveries"]) == 0
    output = capsys.readouterr().out
    assert "provider_status_conflict" in output and "state=read" in output
    assert CUSTOMER not in output and MESSAGE_ID not in output and PRIVATE_TEXT not in output
    opaque = store.automation_identifier(inbound_id)
    assert store.get_automation_state(opaque)["unresolved_delivery"]
    next_inbound = InboundMessage("telnyx", "next", CUSTOMER, PHONE, "Synthetic next")
    next_claim = store.claim_generation(next_inbound, now=TIME)
    assert not next_claim.acquired and next_claim.blocked_by_predecessor
    assert all(item.blocked_by_predecessor for item in store.list_pending_generations(now=TIME))
    state = store.get_automation_state(opaque)
    state = store.change_automation(
        opaque, "pause", "a" * 32, state["revision"], "operator", now=TIME
    )
    state = store.change_automation(
        opaque, "resume", "b" * 32, state["revision"], "operator", now=TIME
    )
    assert state["unresolved_delivery"]
    assert rows(path, "outbound_deliveries")[0]["status_conflict"] == 1


def test_conflict_fences_already_claimed_next_delivery(ingress, private_key):
    _, store, path = ingress
    pending(store)
    accept(store)
    pending(store, message_id="next")
    next_delivery = store.claim_next_delivery(now=TIME)
    assert next_delivery is not None
    receive(ingress, private_key, status_wire("delivered"), status_wire("failed"))
    assert not store.authorize_delivery_submission(
        delivery_id=next_delivery.delivery_id,
        owner_token=next_delivery.owner_token,
        now=TIME,
    )
    assert rows(path, "outbound_deliveries")[1]["submission_started_at"] is None


def test_lost_ack_restart_replay_and_commit_visibility(ingress, private_key, monkeypatch):
    adapter, _, path = ingress
    original = adapter.acknowledge

    def lost():
        assert len(rows(path, "delivery_status_events")) == 1
        raise ConnectionError("Synthetic lost ACK")

    monkeypatch.setattr(adapter, "acknowledge", lost)
    with pytest.raises(ConnectionError):
        receive(ingress, private_key, status_wire())
    monkeypatch.setattr(adapter, "acknowledge", original)
    store = SqliteConversationStore(path)
    store.initialize()
    receive((adapter, store, path), private_key, status_wire())
    pending(store)
    accept(store)
    receive((adapter, SqliteConversationStore(path), path), private_key, status_wire())
    assert len(rows(path, "delivery_status_events")) == 1
    assert rows(path, "outbound_deliveries")[0]["state"] == "delivered"


def test_database_failure_rolls_back_entire_mixed_batch_and_redacts(ingress, private_key, caplog):
    _, _, path = ingress
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER synthetic_failure BEFORE INSERT ON delivery_status_events "
            "BEGIN SELECT RAISE(ABORT, 'PRIVATE-content-Lívia-✨'); END"
        )
    with pytest.raises(PersistenceUnavailable) as caught:
        receive(ingress, private_key, wire(), status_wire())
    assert PRIVATE_TEXT not in "".join(traceback.format_exception(caught.value)) + caplog.text
    assert rows(path, "inbound_event_receipts") == []
    assert rows(path, "messages") == []
    assert rows(path, "delivery_status_events") == []


def test_reconciliation_failure_rolls_back_acceptance_and_link(ingress, private_key):
    _, store, path = ingress
    pending(store)
    receive(ingress, private_key, status_wire())
    claim = claim_delivery(store)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TRIGGER synthetic_failure BEFORE UPDATE OF state ON outbound_deliveries "
            "WHEN NEW.state='delivered' BEGIN "
            "SELECT RAISE(ABORT, 'private synthetic failure'); END"
        )
    with pytest.raises(PersistenceUnavailable) as caught:
        accept(store, claim)
    assert "private synthetic failure" not in "".join(traceback.format_exception(caught.value))
    assert rows(path, "outbound_deliveries")[0]["state"] == "sending"
    assert rows(path, "delivery_attempts")[0]["outcome"] == "started"
    assert rows(path, "delivery_status_events")[0]["delivery_id"] is None
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER synthetic_failure")
    assert accept(store, claim).state == DeliveryState.DELIVERED


def test_commit_failure_has_no_ack_or_receipt(ingress, private_key, monkeypatch):
    _, store, path = ingress
    original = store._connect

    @contextmanager
    def broken(*args, **kwargs):
        with original(*args, **kwargs) as connection:
            yield connection
            raise sqlite3.OperationalError(PRIVATE_TEXT)

    monkeypatch.setattr(store, "_connect", broken)
    with pytest.raises(PersistenceUnavailable):
        receive(ingress, private_key, status_wire())
    assert rows(path, "delivery_status_events") == []


def test_concurrent_acceptance_and_callback_converge(ingress, private_key):
    adapter, store, path = ingress
    pending(store)
    claim = claim_delivery(store)
    barrier = Barrier(2)

    def callback():
        barrier.wait(timeout=5)
        return receive((adapter, SqliteConversationStore(path), path), private_key, status_wire())

    def acceptance():
        barrier.wait(timeout=5)
        return accept(SqliteConversationStore(path), claim)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(callback), pool.submit(acceptance)]
        for future in futures:
            future.result(timeout=10)
    assert rows(path, "outbound_deliveries")[0]["state"] == "delivered"
    assert len(rows(path, "delivery_status_events")) == 1


def test_migration_preserves_legacy_inbox_and_does_not_promote_telnyx_rows(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    manager = MigrationManager(path)
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda config, _: original(config, "0018_inbound_event_receipts")
        )
        manager.upgrade()
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO pending_delivery_statuses(provider,provider_message_id,status,"
            "received_at,updated_at) VALUES (?,?,'read',?,?)",
            [
                (p, MESSAGE_ID, TIME.isoformat(), TIME.isoformat())
                for p in ("meta", "twilio", "telnyx")
            ],
        )
    manager.upgrade()
    manager.upgrade()
    store = SqliteConversationStore(path)
    pending(store)
    assert accept(store).state == DeliveryState.ACCEPTED
    assert len(rows(path, "pending_delivery_statuses")) == 3
    assert rows(path, "delivery_status_events") == []


def test_conflict_cannot_be_erased_by_legacy_maintenance(ingress, private_key):
    _, store, path = ingress
    pending(store)
    accept(store)
    receive(ingress, private_key, status_wire("read"), status_wire("failed"))
    before = rows(path, "outbound_deliveries")
    with pytest.raises(PersistenceUnavailable):
        store.purge_messages_older_than(TIME + timedelta(days=100))
    with pytest.raises(PersistenceUnavailable):
        store.delete_conversation(provider="telnyx", customer_address=CUSTOMER)
    assert rows(path, "outbound_deliveries") == before
    assert len(store.list_blocked_deliveries()) == 1


def test_status_receipts_survive_raw_message_purge(ingress, private_key):
    adapter, store, path = ingress
    pending(store)
    accept(store)
    receive(ingress, private_key, status_wire("read"))
    before = rows(path, "delivery_status_events")
    store.purge_messages_older_than(TIME + timedelta(days=100))
    assert rows(path, "messages") == []
    assert rows(path, "delivery_status_events") == before
    receive((adapter, SqliteConversationStore(path), path), private_key, status_wire("read"))
    assert rows(path, "delivery_status_events") == before
    assert rows(path, "messages") == []


def test_early_scope_does_not_admit_arbitrary_canonical_telnyx_status(ingress):
    from rj_studio_ai.domain import DeliveryStatus

    _, store, path = ingress
    with pytest.raises(ValueError, match="provenance"):
        store.record_delivery_status(
            DeliveryStatusReceived("telnyx", MESSAGE_ID, DeliveryStatus.READ)
        )
    assert rows(path, "pending_delivery_statuses") == []
    assert rows(path, "delivery_status_events") == []


def test_sqlite_writer_lock_deadline_prevents_ack(ingress, private_key):
    _, _, path = ingress
    with sqlite3.connect(path) as lock:
        lock.execute("BEGIN IMMEDIATE")
        with pytest.raises(PersistenceUnavailable):
            receive(
                ingress,
                private_key,
                status_wire(),
                deadline=ExecutionDeadline.start(total_seconds=0.02, finalization_margin_seconds=0),
            )
    assert rows(path, "delivery_status_events") == []


def test_concurrent_duplicates_have_one_durable_receipt(ingress, private_key):
    adapter, _, path = ingress
    barrier = Barrier(2)

    def callback():
        barrier.wait(timeout=5)
        return receive((adapter, SqliteConversationStore(path), path), private_key, status_wire())

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(callback), pool.submit(callback)]
        assert all(future.result(timeout=10).status_code == 204 for future in futures)
    assert len(rows(path, "delivery_status_events")) == 1


def test_migration_interruption_preserves_data_and_old_schema(tmp_path, monkeypatch):
    from sqlalchemy import event as sqlalchemy_event
    from sqlalchemy.engine import Engine

    path = tmp_path / "interrupted.db"
    manager = MigrationManager(path)
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda config, _: original(config, "0018_inbound_event_receipts")
        )
        manager.upgrade()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO pending_delivery_statuses(provider,provider_message_id,status,"
            "received_at,updated_at) VALUES ('twilio',?,'read',?,?)",
            (MESSAGE_ID, TIME.isoformat(), TIME.isoformat()),
        )
    before = rows(path, "pending_delivery_statuses")

    def fail(connection, cursor, statement, parameters, context, executemany):
        if "CREATE TRIGGER delivery_conflict_rejects_submission" in statement:
            raise RuntimeError("Synthetic migration interruption")

    sqlalchemy_event.listen(Engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Synthetic"):
            manager.upgrade()
    finally:
        sqlalchemy_event.remove(Engine, "after_cursor_execute", fail)
    assert rows(path, "pending_delivery_statuses") == before
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "0018_inbound_event_receipts"
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='delivery_status_events'"
            ).fetchone()
            is None
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    manager.upgrade()
    assert rows(path, "pending_delivery_statuses") == before


@pytest.mark.parametrize(
    "structure,kind",
    [
        ("ix_delivery_status_message", "INDEX"),
        ("telnyx_status_evidence_monotonic", "TRIGGER"),
        ("delivery_conflict_rejects_submission", "TRIGGER"),
    ],
)
def test_schema_verification_requires_status_safety_structures(ingress, structure, kind):
    _, store, path = ingress
    assert store.migrations_are_current()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP {kind} {structure}")
    assert not store.migrations_are_current()


def test_purged_receipt_cannot_bind_to_reused_sqlite_ids(ingress, private_key):
    _, store, path = ingress
    pending(store)
    accept(store)
    receive(ingress, private_key, status_wire("read"))
    old = rows(path, "delivery_status_events")
    store.purge_messages_older_than(TIME + timedelta(days=100))
    pending(store, message_id="new-inbound")
    claim = claim_delivery(store)
    # SQLite integer PKs can be reused. An acceptance owner token cannot.
    assert claim.delivery_id == old[0]["delivery_id"]
    with pytest.raises(ValueError, match="scope mismatch"):
        accept(store, claim)
    assert rows(path, "delivery_status_events") == old
    assert rows(path, "outbound_deliveries")[0]["state"] == "sending"
