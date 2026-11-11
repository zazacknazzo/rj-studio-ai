"""Signed synthetic envelopes through real SQLite; no Telnyx API or commercial data."""

import json
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from test_generation_pause import complete, runner
from test_operational_event_journal import rows
from test_outbound_pause import authorize
from test_telnyx_authentication import (
    NOW,
    PHONE,
    PRIVATE_TEXT,
    lifecycle,
    message,
    signed,
)
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import (
    HumanMessageObserved,
    InboundMessageReceived,
    MessageEdited,
    MessageRevoked,
)
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import InvalidWebhookPayload, InvalidWebhookSignature
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.providers.telnyx_messages import TelnyxMessageAdapter
from rj_studio_ai.webhook_ingress import receive_telnyx_messages

TIME = datetime.fromtimestamp(NOW, UTC)
CUSTOMER = "+15555550101"


def wire(kind="text", *, event_id=None, message_id=None, source=NOW - 1, occurred=NOW):
    result = message("message.echo" if kind == "echo" else "message.received")
    data = result["data"]
    data["id"] = event_id or "event-" + kind
    data["occurred_at"] = datetime.fromtimestamp(occurred, UTC).isoformat()
    payload = data["payload"]
    payload["id"] = message_id or "message-" + kind
    payload["body"] = {
        "id": payload["id"],
        "foreign_id": "wamid.synthetic-" + kind,
        "from": CUSTOMER,
        "timestamp": str(source),
        "type": kind,
    }
    if kind == "echo":
        payload["origin"] = "whatsapp_business_app"
        payload["body"]["type"] = "text"
    if kind in ("text", "echo"):
        payload["body"]["text"] = {"body": PRIVATE_TEXT}
    if kind in ("edit", "revoke"):
        payload["body"][kind] = {"original_message_id": "opaque-original"}
        if kind == "edit":
            payload["body"][kind]["message"] = {"type": "text", "text": {"body": PRIVATE_TEXT}}
    return result


@pytest.fixture
def ingress(settings, private_key, tmp_path):
    path = tmp_path / "telnyx.db"
    store = SqliteConversationStore(path)
    store.initialize()
    adapter = TelnyxMessageAdapter(settings, clock=lambda: NOW)
    return adapter, store, path


def receive(ingress, private_key, *payloads, deadline=None, now=TIME):
    adapter, store, _ = ingress
    return receive_telnyx_messages(
        tuple(signed(private_key, payload) for payload in payloads),
        adapter=adapter,
        store=store,
        deadline=deadline or ExecutionDeadline.start(),
        now=now,
    )


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("text", InboundMessageReceived),
        ("echo", HumanMessageObserved),
        ("edit", MessageEdited),
        ("revoke", MessageRevoked),
    ],
)
def test_signed_classification_and_durable_ack(ingress, private_key, monkeypatch, kind, expected):
    adapter, store, path = ingress
    event = adapter.receive(signed(private_key, wire(kind))).events[0]
    assert type(event) is expected
    assert event.provider_message_id == "message-" + kind
    assert event.metadata.event_id == "event-" + kind
    assert event.metadata.message_aliases[0].namespace == "meta"
    assert event.metadata.message_occurred_at == TIME - timedelta(seconds=1)
    assert event.customer_address == CUSTOMER
    if kind != "text":
        assert PRIVATE_TEXT not in repr(event)
    fake = DeterministicFakeOutboundSender(outcomes=[])
    original_ack = adapter.acknowledge

    def ack():
        # Independent connection observes COMMITTED data, not an uncommitted local row.
        assert (
            len(rows(path, "inbound_event_receipts" if kind == "text" else "operational_events"))
            == 1
        )
        if kind == "echo":
            assert rows(path, "human_pause_effects")[0]["revision"] == 1
            assert rows(path, "conversation_automation_controls")[0]["paused"] == 1
        return original_ack()

    monkeypatch.setattr(adapter, "acknowledge", ack)
    response = receive(ingress, private_key, wire(kind))
    assert response.status_code == 204 and response.body == ""
    assert fake.calls == []
    assert len(rows(path, "messages")) == (1 if kind == "text" else 0)
    assert len(rows(path, "message_processing")) == (1 if kind == "text" else 0)
    assert rows(path, "outbound_deliveries") == []
    if kind != "text":
        assert runner(store).run_once() is None


@pytest.mark.parametrize(
    "content", [{}, {"type": "image"}, {"type": "future"}, {"type": "text", "text": {}}]
)
def test_echo_content_never_becomes_input(ingress, private_key, content):
    payload = wire("echo")
    body = payload["data"]["payload"]["body"]
    body.pop("text")
    body.pop("type")
    body.update(content)
    receive(ingress, private_key, payload)
    assert rows(ingress[2], "messages") == []
    assert len(rows(ingress[2], "human_pause_effects")) == 1


@pytest.mark.parametrize("kind", ["text", "echo", "edit", "revoke"])
def test_lost_ack_restart_and_repeated_envelopes(ingress, private_key, monkeypatch, kind):
    adapter, store, path = ingress
    original = adapter.acknowledge

    def lost_ack():
        raise ConnectionError("synthetic lost ACK")

    monkeypatch.setattr(adapter, "acknowledge", lost_ack)
    with pytest.raises(ConnectionError):
        receive(ingress, private_key, wire(kind))
    monkeypatch.setattr(adapter, "acknowledge", original)
    reopened = SqliteConversationStore(path)
    reopened.initialize()
    replay = (adapter, reopened, path)
    receive(replay, private_key, wire(kind))
    receive(replay, private_key, wire(kind, event_id="different-envelope"))
    table = "inbound_event_receipts" if kind == "text" else "operational_events"
    assert len(rows(path, table)) == 2
    assert len(rows(path, "messages")) == (1 if kind == "text" else 0)
    assert len(rows(path, "human_pause_effects")) == (1 if kind == "echo" else 0)


@pytest.mark.parametrize("kind", ["text", "echo"])
def test_concurrent_duplicate_requests(ingress, private_key, kind):
    adapter, _, path = ingress
    barrier = Barrier(2)

    def worker(index):
        barrier.wait(timeout=5)
        return receive(
            (adapter, SqliteConversationStore(path), path),
            private_key,
            wire(kind, event_id=f"event-{index}"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(r.status_code == 204 for r in pool.map(worker, range(2)))
    assert len(rows(path, "human_pause_effects" if kind == "echo" else "messages")) == 1


def resumed(ingress, private_key):
    receive(ingress, private_key, wire("echo"), now=TIME - timedelta(seconds=5))
    _, store, path = ingress
    with sqlite3.connect(path) as connection:
        opaque = connection.execute("SELECT opaque_id FROM conversation_operation_ids").fetchone()[
            0
        ]
    store.change_automation(
        opaque, "resume", uuid4().hex, 1, "synthetic-operator", now=TIME - timedelta(seconds=2)
    )
    return opaque


@pytest.mark.parametrize(
    "source", [NOW - 3, NOW - 2, None, "bad", True, 1.5, "9" * 100, str(NOW + 1), "-1"]
)
def test_old_or_unproven_inbound_suppressed_after_resume(ingress, private_key, source):
    resumed(ingress, private_key)
    payload = wire()
    if source is None:
        payload["data"]["payload"]["body"].pop("timestamp")
    else:
        payload["data"]["payload"]["body"]["timestamp"] = (
            str(source) if type(source) is int else source
        )
    receive(ingress, private_key, payload)
    assert rows(ingress[2], "message_processing")[0]["state"] == "suppressed"
    assert runner(ingress[1]).run_once() is None


def test_new_inbound_eligible_and_late_echo_repauses(ingress, private_key):
    opaque = resumed(ingress, private_key)
    receive(ingress, private_key, wire("echo", event_id="echo-replay"))
    assert not ingress[1].get_automation_state(opaque)["paused"]
    receive(ingress, private_key, wire())
    claim = ingress[1].claim_generation(
        ingress[0].receive(signed(private_key, wire())).events[0], now=TIME
    )
    assert claim.acquired
    # Same Meta alias, DIFFERENT logical Message is new conservative activity.
    receive(
        ingress,
        private_key,
        wire(
            "echo", event_id="late", message_id="late-human", source=NOW - 1000, occurred=NOW - 900
        ),
    )
    assert ingress[1].get_automation_state(opaque)["paused"]
    assert not complete(ingress[1], claim, now=TIME)
    assert rows(ingress[2], "outbound_deliveries") == []


@pytest.mark.parametrize("source,event_time", [(NOW - 1, NOW - 2), (NOW - 1, NOW + 1)])
def test_contradictory_or_future_event_time_does_not_bypass_resume(
    ingress, private_key, source, event_time
):
    resumed(ingress, private_key)
    receive(ingress, private_key, wire(source=source, occurred=event_time))
    assert rows(ingress[2], "message_processing")[0]["state"] == "suppressed"


@pytest.mark.parametrize("kind", ["text", "echo", "edit", "revoke"])
def test_hidden_phone_uses_opaque_namespace(ingress, private_key, kind):
    payload = wire(kind)
    p = payload["data"]["payload"]
    p["body"]["from"] = ""
    p["body"]["from_user_id"] = "US.synthetic-123"
    if kind == "echo":
        p["to"] = "US.synthetic-123"
    else:
        p["from"]["phone_number"] = ""
    event = ingress[0].receive(signed(private_key, payload)).events[0]
    assert event.customer_address == "bsuid:US.synthetic-123"
    receive(ingress, private_key, payload)


@pytest.mark.parametrize(
    "original", ["wamid.original", "00000000-0000-4000-8000-000000000001", "opaque-original"]
)
@pytest.mark.parametrize("kind", ["edit", "revoke"])
def test_original_reference_is_always_opaque_and_never_changes_history(
    ingress, private_key, original, kind
):
    receive(ingress, private_key, wire())
    before = rows(ingress[2], "messages")
    payload = wire(kind)
    payload["data"]["payload"]["body"][kind]["original_message_id"] = original
    receive(ingress, private_key, payload)
    assert rows(ingress[2], "messages") == before
    event = rows(ingress[2])[0]
    assert event["original_namespace"] == "telnyx_original_opaque"
    assert event["original_message_id"] == original


@pytest.mark.parametrize(
    "path,value",
    [
        (("data", "id"), ""),
        (("data", "id"), 12),
        (("data", "occurred_at"), "2026-01-01"),
        (("data", "payload", "id"), None),
        (("data", "payload", "body", "id"), "other-message"),
        (("data", "payload", "body", "foreign_id"), []),
        (("data", "payload", "body", "text", "body"), " "),
        (("data", "payload", "body", "text", "body"), 42),
        (("data", "payload", "body", "text", "body"), "\ud800"),
        (("data", "payload", "body", "type"), "image"),
        (("data", "payload", "body", "type"), "location"),
        (("data", "payload", "body", "type"), "file"),
        (("data", "payload", "body", "type"), []),
        (("data", "payload", "body", "from"), "+15555550999"),
        (("data", "payload", "from", "phone_number"), "opaque-unverified"),
        (("data", "payload", "to"), [PHONE]),
        (("data", "payload", "to"), "+15555550999"),
        (("data", "payload", "direction"), "outbound"),
        (("data", "payload", "organization_id"), "wrong"),
        (("data", "payload", "messaging_profile_id"), "wrong"),
        (("data", "event_type"), "whatsapp.messages"),
        (("data", "event_type"), "unknown"),
    ],
)
def test_invalid_or_unsupported_payload_never_acks(ingress, private_key, monkeypatch, path, value):
    payload = wire()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    acked = []
    monkeypatch.setattr(ingress[0], "acknowledge", lambda: acked.append(True))
    # ensure_ascii also allows us to send an unpaired surrogate as legal JSON escape.
    request = signed(private_key, body=json.dumps(payload).encode())
    with pytest.raises(InvalidWebhookPayload):
        receive_telnyx_messages(
            (request,),
            adapter=ingress[0],
            store=ingress[1],
            deadline=ExecutionDeadline.start(),
            now=TIME,
        )
    assert not acked
    for table in ("messages", "operational_events", "inbound_event_receipts", "conversations"):
        assert rows(ingress[2], table) == []


@pytest.mark.parametrize("origin", [None, "api", "", {}, "whatsapp_business_app "])
def test_wrong_echo_origin_rejected(ingress, private_key, origin):
    payload = wire("echo")
    payload["data"]["payload"]["origin"] = origin
    with pytest.raises(InvalidWebhookPayload):
        receive(ingress, private_key, payload)
    assert rows(ingress[2]) == []


@pytest.mark.parametrize(
    "event_type", ["message.sent", "message.read", "message.finalized", "whatsapp.account.update"]
)
def test_future_ticket_events_authenticated_but_not_acked(ingress, private_key, event_type):
    payload = lifecycle() if event_type == "whatsapp.account.update" else message(event_type)
    with pytest.raises(InvalidWebhookPayload):
        receive(ingress, private_key, payload)
    assert rows(ingress[2]) == []


@pytest.mark.parametrize("body", [b"{malformed", b'{"data":{},"data":{}}', b"[]"])
def test_malformed_json_and_unsigned_requests_have_no_effect(ingress, private_key, body):
    request = signed(private_key, body=body)
    with pytest.raises(InvalidWebhookSignature):
        receive_telnyx_messages(
            (replace(request, headers={}),),
            adapter=ingress[0],
            store=ingress[1],
            deadline=ExecutionDeadline.start(),
        )
    with pytest.raises(InvalidWebhookPayload):
        receive_telnyx_messages(
            (request,), adapter=ingress[0], store=ingress[1], deadline=ExecutionDeadline.start()
        )
    assert rows(ingress[2], "conversations") == []


@pytest.mark.parametrize("failure", ["statement", "commit", "conflict", "unsupported"])
def test_mixed_batch_rolls_back_every_effect_before_ack(ingress, private_key, monkeypatch, failure):
    adapter, store, path = ingress
    acked = []
    monkeypatch.setattr(adapter, "acknowledge", lambda: acked.append(True))
    payloads = [wire(), wire("echo"), wire("edit"), wire("revoke")]
    if failure == "statement":
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TRIGGER synthetic_failure BEFORE INSERT ON operational_events "
                "WHEN NEW.kind='message_revocation' BEGIN "
                "SELECT RAISE(ABORT,'PRIVATE-SQL-SENTINEL'); END"
            )
    elif failure == "commit":
        original = store._connect

        @contextmanager
        def failed_commit(*args, **kwargs):
            with original(*args, **kwargs) as connection:
                connection.execute("PRAGMA defer_foreign_keys=ON")
                yield connection
                connection.execute(
                    "INSERT INTO operational_event_aliases VALUES (-1,'ns','synthetic')"
                )

        monkeypatch.setattr(store, "_connect", failed_commit)
    elif failure == "conflict":
        payloads[-1]["data"]["id"] = "event-text"
    else:
        payloads.append(wire("image"))
    with pytest.raises((PersistenceUnavailable, ValueError)) as error:
        receive(ingress, private_key, *payloads)
    assert "PRIVATE-SQL-SENTINEL" not in "".join(traceback.format_exception(error.value))
    assert acked == []
    for table in (
        "messages",
        "message_processing",
        "conversations",
        "operational_events",
        "inbound_event_receipts",
        "human_pause_effects",
        "conversation_automation_controls",
    ):
        assert rows(path, table) == []


def test_successful_mixed_batch_pauses_before_ack(ingress, private_key):
    receive(ingress, private_key, wire(), wire("echo"), wire("edit"), wire("revoke"))
    assert rows(ingress[2], "message_processing")[0]["state"] == "suppressed"
    assert len(rows(ingress[2])) == 3
    assert len(rows(ingress[2], "inbound_event_receipts")) == 1


@pytest.mark.parametrize("phase", ["before_parse", "before_commit", "after_commit", "locked"])
def test_ingress_deadline_never_returns_late_success(ingress, private_key, monkeypatch, phase):
    adapter, store, path = ingress
    clock = [0.0]
    deadline = ExecutionDeadline.start(
        clock=lambda: clock[0], total_seconds=1, finalization_margin_seconds=0
    )
    acked = []
    monkeypatch.setattr(adapter, "acknowledge", lambda: acked.append(True))
    if phase == "before_parse":
        clock[0] = 2.0
    elif phase in ("before_commit", "after_commit"):
        original = store._connect

        @contextmanager
        def expire(*args, **kwargs):
            with original(*args, **kwargs) as connection:
                if phase == "before_commit":
                    connection.set_trace_callback(
                        lambda sql: (
                            clock.__setitem__(0, 2.0) if "INSERT INTO messages" in sql else None
                        )
                    )
                yield connection
            if phase == "after_commit":
                clock[0] = 2.0

        monkeypatch.setattr(store, "_connect", expire)
    with sqlite3.connect(path) as lock:
        if phase == "locked":
            lock.execute("BEGIN IMMEDIATE")
            # Real SQLITE_BUSY with zero lock budget, no sleep-dependent race.
            store._busy_timeout_seconds = 0
        with pytest.raises(PersistenceUnavailable):
            receive(ingress, private_key, wire(), deadline=deadline)
    assert acked == []
    assert len(rows(path, "messages")) == (1 if phase == "after_commit" else 0)


@pytest.mark.parametrize("same_event", [False, True])
@pytest.mark.parametrize("mutation", ["customer", "channel", "content", "kind"])
def test_conflicting_identity_is_not_silently_deduplicated(
    ingress, private_key, same_event, mutation
):
    receive(ingress, private_key, wire())
    event = ingress[0].receive(signed(private_key, wire())).events[0]
    if not same_event:
        event = replace(event, metadata=replace(event.metadata, event_id="new-envelope"))
    if mutation == "customer":
        event = replace(event, customer_address="different-customer")
    elif mutation == "channel":
        event = replace(event, recipient_address="different-channel")
    elif mutation == "content":
        event = replace(event, body="different-content")
    else:
        echo = ingress[0].receive(signed(private_key, wire("echo"))).events[0]
        event = replace(
            echo,
            provider_message_id=event.provider_message_id,
            metadata=replace(echo.metadata, event_id=event.metadata.event_id),
        )
    with pytest.raises(ValueError):
        ingress[1].record_webhook_events((event,), now=TIME, require_message_provenance=True)
    assert len(rows(ingress[2], "inbound_event_receipts")) == 1
    assert rows(ingress[2], "human_pause_effects") == []


@pytest.mark.parametrize("echo_first", [False, True])
@pytest.mark.parametrize("boundary", ["generation", "authorization"])
def test_concurrent_echo_fences_generation_and_submission(
    ingress, private_key, monkeypatch, echo_first, boundary
):
    adapter, store, path = ingress
    receive(ingress, private_key, wire())
    generation = store.claim_generation(
        adapter.receive(signed(private_key, wire())).events[0], now=TIME
    )
    assert generation.acquired
    if boundary == "authorization":
        assert complete(store, generation, now=TIME)
        claim = store.claim_next_delivery(now=TIME)
        assert claim is not None
    entered, release, contender = Event(), Event(), Event()
    original = store._connect
    needle = (
        "INSERT INTO human_pause_effects"
        if echo_first
        else "INSERT INTO messages"
        if boundary == "generation"
        else "UPDATE outbound_deliveries AS delivery"
    )

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

    def echo(target):
        return receive((adapter, target, path), private_key, wire("echo"))

    def action(target):
        return (
            complete(target, generation, now=TIME)
            if boundary == "generation"
            else authorize(target, claim, now=TIME)
        )

    def second():
        contender.set()
        return action(other) if echo_first else echo(other)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(echo if echo_first else action, store)
        try:
            assert entered.wait(timeout=5)
            second_future = pool.submit(second)
            assert contender.wait(timeout=5)
        finally:
            release.set()
        first_result = first.result(timeout=5)
        second_result = second_future.result(timeout=5)
    assert (second_result if echo_first else first_result) is (not echo_first)
    assert rows(path, "conversation_automation_controls")[0]["paused"] == 1
    deliveries = rows(path, "outbound_deliveries")
    if boundary == "generation":
        assert len(deliveries) == (0 if echo_first else 1)
        if deliveries:
            assert deliveries[0]["state"] == "cancelled"
    else:
        assert deliveries[0]["state"] == ("cancelled" if echo_first else "sending")
        assert (deliveries[0]["submission_started_at"] is None) is echo_first


def test_no_private_content_or_credentials_in_errors_or_journal(ingress, private_key, caplog):
    payload = wire("echo")
    payload["data"]["payload"]["origin"] = PRIVATE_TEXT
    with pytest.raises(InvalidWebhookPayload) as error:
        receive(ingress, private_key, payload)
    surfaces = "".join(traceback.format_exception(error.value)) + caplog.text
    assert PRIVATE_TEXT not in surfaces and CUSTOMER not in surfaces and PHONE not in surfaces
    receive(ingress, private_key, wire("echo"), wire("edit"), wire("revoke"))
    assert PRIVATE_TEXT not in json.dumps(rows(ingress[2]))
    assert not caplog.records


def test_echo_during_llm_discards_result_without_holding_sqlite(ingress, private_key):
    from test_async_ingress import _BlockingGenerator

    adapter, store, path = ingress
    # The executor uses real current time; signature time is independently fixed.
    receive(ingress, private_key, wire(), now=datetime.now(UTC))
    generator = _BlockingGenerator()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner(store, generator).run_once)
        try:
            assert generator.entered.wait(timeout=5)
            receive((adapter, SqliteConversationStore(path), path), private_key, wire("echo"))
        finally:
            generator.release.set()
        assert future.result(timeout=5) is None
    assert rows(path, "outbound_deliveries") == []
    assert rows(path, "message_processing")[0]["state"] == "suppressed"


def test_purged_inbound_cannot_be_readmitted_by_replay(ingress, private_key):
    receive(ingress, private_key, wire())
    _, store, path = ingress
    store.purge_messages_older_than(TIME + timedelta(days=1))
    assert rows(path, "messages") == []
    store.initialize()
    receive(ingress, private_key, wire(event_id="after-purge"))
    assert rows(path, "messages") == []
    assert len(rows(path, "inbound_event_receipts")) == 2


def test_channel_change_rejected_even_without_pause_control(ingress, private_key, settings):
    receive(ingress, private_key, wire())
    settings.telnyx_phone_number = "+15555550999"
    adapter = TelnyxMessageAdapter(settings, clock=lambda: NOW)
    payload = wire(message_id="new-message", event_id="new-event")
    payload["data"]["payload"]["to"] = settings.telnyx_phone_number
    with pytest.raises(ValueError, match="channel"):
        receive((adapter, ingress[1], ingress[2]), private_key, payload)
    assert len(rows(ingress[2], "messages")) == 1


def test_unresolved_echo_cannot_ack_or_apply_to_ambiguous_conversation(ingress, private_key):
    _, _, path = ingress
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO conversations(provider,customer_address,created_at,updated_at) "
            "VALUES ('telnyx',?,?,?)",
            (CUSTOMER, TIME.isoformat(), TIME.isoformat()),
        )
    with pytest.raises(ValueError, match="Unresolved human activity"):
        receive(ingress, private_key, wire("echo"))
    assert rows(path) == []
    assert rows(path, "human_pause_effects") == []


@pytest.mark.parametrize("index", ["uq_inbound_event_scope", "ix_inbound_event_message"])
def test_missing_inbound_receipt_index_fails_readiness(ingress, index):
    from rj_studio_ai.migrations import MigrationManager

    path = ingress[2]
    assert MigrationManager(path).is_current()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP INDEX {index}")
    assert not MigrationManager(path).is_current()


@pytest.mark.parametrize("interrupt", [False, True])
def test_upgrade_preserves_previous_journal_and_rolls_back_atomically(tmp_path, interrupt):
    from alembic import command
    from sqlalchemy import event as sqlalchemy_event
    from sqlalchemy.engine import Engine
    from test_coexistence_contracts import human

    from rj_studio_ai.migrations import MigrationManager

    path = tmp_path / "migration.db"
    manager = MigrationManager(path)
    engine = manager._engine(set_journal_mode=True)
    with engine.connect() as connection:
        manager._config.attributes["connection"] = connection
        command.upgrade(manager._config, "0017_automation_operations")
    manager._config.attributes.pop("connection")
    engine.dispose()
    store = SqliteConversationStore(path)
    store.record_webhook_events((human(),))
    before = rows(path)
    effects = rows(path, "human_pause_effects")

    def fault(connection, cursor, statement, parameters, context, executemany):
        if "CREATE INDEX ix_inbound_event_message" in statement and interrupt:
            raise RuntimeError("synthetic interruption")

    sqlalchemy_event.listen(Engine, "after_cursor_execute", fault)
    try:
        if interrupt:
            with pytest.raises(RuntimeError):
                manager.upgrade()
        else:
            manager.upgrade()
    finally:
        sqlalchemy_event.remove(Engine, "after_cursor_execute", fault)
    assert rows(path) == before and rows(path, "human_pause_effects") == effects
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0017_automation_operations" if interrupt else "0018_inbound_event_receipts"
        )
        if interrupt:
            assert (
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='inbound_event_receipts'"
                ).fetchall()
                == []
            )
