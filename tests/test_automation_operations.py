import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_coexistence_contracts import NOW, human, inbound
from test_generation_pause import complete
from test_operational_event_journal import identified

from rj_studio_ai.automation_operations import OperationConflict
from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)

SECRET = "synthetic-test-operator-credential-only"


def test_authenticated_query_is_private_and_read_only(tmp_path):
    store = SqliteConversationStore(tmp_path / "operations.db")
    store.initialize()
    claim = store.admit_generation(inbound())
    opaque = store.automation_identifier(claim.inbound_message_id)
    settings = Settings(
        _env_file=None,
        operator_secret_sha256=hashlib.sha256(SECRET.encode()).hexdigest(),
        operator_id="operator-test",
        operator_permissions=("read", "control"),
        operator_conversations=("*",),
    )
    client = TestClient(create_app(settings, store=store))
    url = f"/admin/conversations/{opaque}/automation"
    assert client.get(url).status_code == 401
    response = client.get(url, headers={"Authorization": f"Bearer {SECRET}"})
    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": opaque,
        "paused": False,
        "revision": 0,
        "handoff_active": False,
        "in_flight_possible": False,
        "unresolved_delivery": False,
    }
    assert "customer" not in response.text and SECRET not in response.text
    assert client.get(url, headers={"Authorization": f"Bearer {SECRET}"}).json() == response.json()


def test_pause_resume_are_durable_cas_and_idempotent(tmp_path):
    from uuid import uuid4

    store = SqliteConversationStore(tmp_path / "ops.db")
    store.initialize()
    claim = store.claim_generation(inbound())
    opaque = store.automation_identifier(claim.inbound_message_id)
    key = uuid4().hex
    first = store.change_automation(opaque, "pause", key, 0, "operator-test")
    assert first["paused"] and first["revision"] == 1
    assert store.change_automation(opaque, "pause", key, 0, "operator-test") == first
    resumed = store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    assert not resumed["paused"] and resumed["revision"] == 2
    assert not store.claim_generation(inbound()).acquired
    reopened = SqliteConversationStore(tmp_path / "ops.db")
    reopened.initialize()
    assert reopened.get_automation_state(opaque) == resumed


@pytest.fixture
def ops(tmp_path):
    store = SqliteConversationStore(tmp_path / "ops.db")
    store.initialize()
    claim = store.admit_generation(inbound())
    opaque = store.automation_identifier(claim.inbound_message_id)
    return store, opaque, tmp_path / "ops.db"


def api(store, **changes):
    values = dict(
        _env_file=None,
        operator_secret_sha256=hashlib.sha256(SECRET.encode()).hexdigest(),
        operator_id="operator-test",
        operator_permissions=("read", "control"),
        operator_conversations=("*",),
    )
    values.update(changes)
    return TestClient(create_app(Settings(**values), store=store))


def request(client, opaque, action, revision=0, key=None, token=SECRET):
    return client.post(
        f"/admin/conversations/{opaque}/automation/{action}",
        headers={"Authorization": f"Bearer {token}"},
        json={"operation_id": key or uuid4().hex, "expected_revision": revision},
    )


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"operator_secret_sha256": ""}, 503),
        ({"operator_secret_sha256": "invalid"}, 503),
        ({"operator_id": ""}, 503),
        ({"operator_permissions": ()}, 503),
        ({"operator_permissions": ("unknown",)}, 503),
        ({"operator_conversations": ()}, 503),
        ({"operator_conversations": ("not-an-id",)}, 503),
        ({"operator_permissions": ("read",)}, 403),
        ({"operator_conversations": ("a" * 32,)}, 403),
    ],
)
def test_fail_closed_configuration_and_authorization(ops, changes, status):
    store, opaque, _ = ops
    assert request(api(store, **changes), opaque, "pause").status_code == status
    assert store.get_automation_state(opaque)["revision"] == 0


@pytest.mark.parametrize("token", ["", "invalid", "owner-token", "episode-token", "1", "z" * 40])
def test_wrong_credentials_cannot_inspect_or_mutate(ops, token):
    store, opaque, _ = ops
    client = api(store)
    assert (
        client.get(
            f"/admin/conversations/{opaque}/automation",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 401
    )
    assert request(client, opaque, "pause", token=token).status_code == 401
    assert store.get_automation_state(opaque)["revision"] == 0


def test_api_commands_receipts_conflicts_and_redaction(ops, caplog):
    store, opaque, _ = ops
    client = api(store)
    key = uuid4().hex
    first = request(client, opaque, "pause", key=key)
    assert first.status_code == 200 and first.json()["paused"]
    assert request(client, opaque, "pause", key=key).json() == first.json()
    assert request(client, opaque, "resume", revision=1, key=key).status_code == 409
    assert request(client, opaque, "resume", revision=0).status_code == 409
    assert request(client, opaque, "resume", revision=1).json()["revision"] == 2
    assert request(client, opaque, "pause", key=key).json() == first.json()
    assert not store.get_automation_state(opaque)["paused"]
    response = client.post(
        f"/admin/conversations/{opaque}/automation/pause",
        headers={"Authorization": f"Bearer {SECRET}"},
        json={"password": SECRET},
    )
    assert response.status_code == 422
    assert SECRET not in response.text + caplog.text
    assert client.get(f"/admin/conversations/{opaque}/automation?token={SECRET}").status_code == 401


@pytest.mark.parametrize("mode", ["same_key", "resume_race", "pause_resume"])
def test_concurrent_commands_have_single_cas_winner(ops, mode):
    store, opaque, path = ops
    store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    barrier = Barrier(2)
    key = uuid4().hex

    def change(i):
        barrier.wait(timeout=5)
        try:
            return SqliteConversationStore(path).change_automation(
                opaque,
                "pause" if mode == "pause_resume" and i else "resume",
                key if mode == "same_key" else uuid4().hex,
                1,
                "operator-test",
            )
        except OperationConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, range(2)))
    assert sum(x is not None for x in results) == (2 if mode == "same_key" else 1)
    assert store.get_automation_state(opaque)["revision"] == 2


@pytest.mark.parametrize(
    "kind", ["duplicate", "other_envelope", "old_timestamp", "new", "ambiguous_alias"]
)
def test_echo_resolution_after_resume_is_conservative(ops, kind):
    store, opaque, _ = ops
    store.record_webhook_events((human(),), now=NOW)
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    event = human()
    if kind == "other_envelope":
        event = identified(event, "other-envelope")
    elif kind in ("old_timestamp", "new", "ambiguous_alias"):
        event = replace(identified(event, "new-envelope"), provider_message_id="new-human")
        if kind == "old_timestamp":
            event = replace(
                event, metadata=replace(event.metadata, occurred_at=NOW - timedelta(days=300))
            )
        if kind == "ambiguous_alias":
            from rj_studio_ai.domain import MessageReference

            event = replace(
                event,
                metadata=replace(
                    event.metadata,
                    message_aliases=(MessageReference("synthetic", "message-human"),),
                ),
            )
    store.record_webhook_events((event,), now=NOW)
    state = store.get_automation_state(opaque)
    assert state["paused"] == (kind not in ("duplicate", "other_envelope"))
    assert state["revision"] == (2 if kind in ("duplicate", "other_envelope") else 3)


def test_pause_fences_generation_and_resume_only_allows_new_inbound(ops):
    store, opaque, _ = ops
    claim = store.claim_generation(inbound())
    store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    assert not complete(store, claim)
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    assert store.claim_generation(inbound()).state is GenerationState.SUPPRESSED
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    future = replace(
        inbound(),
        provider_message_id="future",
        metadata=replace(inbound().metadata, occurred_at=now, message_occurred_at=now),
    )
    assert store.claim_generation(future, now=now).acquired


@pytest.mark.parametrize("marked", [False, True])
def test_manual_pause_fences_claimed_outbound_and_preserves_possible_submission(ops, marked):
    store, opaque, _ = ops
    claim = store.claim_generation(inbound(), now=NOW)
    assert complete(store, claim)
    delivery = store.claim_next_delivery(now=NOW)
    if marked:
        assert store.authorize_delivery_submission(
            delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=NOW
        )
    result = store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    assert result["in_flight_possible"] == marked
    assert not store.authorize_delivery_submission(
        delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=NOW
    )
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    assert store.get_delivery(delivery.delivery_id).state is (
        DeliveryState.SENDING if marked else DeliveryState.CANCELLED
    )
    assert store.claim_next_delivery(now=NOW + timedelta(days=1)) is None


def test_handoff_and_unknown_are_not_released(ops):
    store, opaque, _ = ops
    claim = store.claim_generation(inbound())
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Synthetic",
        delivery_state=DeliveryState.UNKNOWN,
        handoff_reason="explicit_human_request",
    )
    before = store.list_active_handoffs()
    store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    resumed = store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    assert resumed["handoff_active"] and resumed["unresolved_delivery"]
    assert store.list_active_handoffs() == before
    assert store.get_delivery_for_inbound(claim.inbound_message_id).state is DeliveryState.UNKNOWN


def test_operation_receipt_failure_rolls_back_pause_and_cancellation(ops):
    store, opaque, path = ops
    claim = store.claim_generation(inbound())
    assert complete(store, claim)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TRIGGER fail_receipt BEFORE INSERT ON automation_operation_receipts "
            "BEGIN SELECT RAISE(ABORT,'private-sentinel'); END"
        )
    with pytest.raises(PersistenceUnavailable) as error:
        store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    assert "private-sentinel" not in str(error.value)
    assert store.get_automation_state(opaque)["revision"] == 0
    assert store.get_delivery_for_inbound(claim.inbound_message_id).state is DeliveryState.PENDING


def test_resource_scope_and_other_conversation_are_independent(ops):
    store, opaque, _ = ops
    other = store.admit_generation(
        replace(inbound(), customer_address="other", provider_message_id="other")
    )
    other_id = store.automation_identifier(other.inbound_message_id)
    client = api(store, operator_conversations=(opaque,))
    assert request(client, other_id, "pause").status_code == 403
    assert request(client, opaque, "pause").status_code == 200
    assert store.get_automation_state(other_id)["revision"] == 0


def test_old_authorized_delivery_cannot_retry_after_pause_resume(ops):
    store, opaque, _ = ops
    claim = store.claim_generation(inbound(), now=NOW)
    assert complete(store, claim)
    delivery = store.claim_next_delivery(now=NOW)
    assert store.authorize_delivery_submission(
        delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=NOW
    )
    store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    assert store.finalize_delivery(
        delivery_id=delivery.delivery_id,
        owner_token=delivery.owner_token,
        outcome=DeliveryState.RETRYABLE,
        safe_error_code="provider_retryable",
        retry_at=NOW + timedelta(seconds=1),
        now=NOW,
    )
    assert store.get_delivery(delivery.delivery_id).state is DeliveryState.CANCELLED
    assert store.claim_next_delivery(now=NOW + timedelta(seconds=2)) is None


@pytest.mark.parametrize("timestamp_case", ["absent", "old", "future", "new"])
def test_resume_suppresses_ambiguous_or_delayed_inbound(ops, timestamp_case):
    from datetime import UTC, datetime

    store, opaque, _ = ops
    store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    now = datetime.now(UTC) + timedelta(seconds=1)
    msg = replace(inbound(), provider_message_id="after-resume")
    if timestamp_case == "absent":
        msg = replace(msg, metadata=None)
    else:
        source = {"old": NOW, "future": now + timedelta(days=1), "new": now}[timestamp_case]
        msg = replace(
            msg, metadata=replace(msg.metadata, occurred_at=source, message_occurred_at=source)
        )
    claim = store.claim_generation(msg, now=now)
    assert claim.acquired == (timestamp_case == "new")
    if timestamp_case != "new":
        assert claim.state is GenerationState.SUPPRESSED


def test_manual_pause_during_llm_invalidates_result_without_database_lock(ops):
    from test_async_ingress import _BlockingGenerator
    from test_generation_pause import runner

    store, opaque, path = ops
    generator = _BlockingGenerator()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner(store, generator).run_once)
        try:
            assert generator.entered.wait(timeout=5)
            assert request(api(SqliteConversationStore(path)), opaque, "pause").status_code == 200
        finally:
            generator.release.set()
        assert future.result(timeout=5) is None
    assert (
        store.get_generation(
            provider="synthetic", provider_message_id=inbound().provider_message_id
        ).state
        is GenerationState.SUPPRESSED
    )


@pytest.mark.parametrize("pause_first", [False, True])
def test_manual_pause_races_delivery_authorization_in_both_orders(ops, monkeypatch, pause_first):
    from contextlib import contextmanager
    from threading import Event

    store, opaque, path = ops
    claim = store.claim_generation(inbound(), now=NOW)
    assert complete(store, claim)
    delivery = store.claim_next_delivery(now=NOW)
    entered, release, contender = Event(), Event(), Event()
    original = store._connect
    needle = (
        "INSERT INTO automation_operation_receipts"
        if pause_first
        else "UPDATE outbound_deliveries AS delivery"
    )

    @contextmanager
    def gated(*args, **kwargs):
        with original(*args, **kwargs) as conn:

            def trace(sql):
                if needle in sql:
                    entered.set()
                    release.wait(timeout=5)

            conn.set_trace_callback(trace)
            yield conn

    monkeypatch.setattr(store, "_connect", gated)

    def pause(target):
        return target.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")

    def authorize(target):
        return target.authorize_delivery_submission(
            delivery_id=delivery.delivery_id, owner_token=delivery.owner_token, now=NOW
        )

    def second():
        contender.set()
        return (authorize if pause_first else pause)(SqliteConversationStore(path))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(pause if pause_first else authorize, store)
        try:
            assert entered.wait(timeout=5)
            next_result = pool.submit(second)
            assert contender.wait(timeout=5)
        finally:
            release.set()
        first_result, second_result = first.result(timeout=5), next_result.result(timeout=5)
    assert (second_result if pause_first else first_result) is (not pause_first)


@pytest.mark.parametrize(
    "missing",
    [
        "automation_operation_receipts",
        "conversation_operation_identity",
        "automation_receipt_immutable",
        "conversation_operation_identity_immutable",
    ],
)
def test_readiness_rejects_missing_operations_structures(ops, missing):
    store, _, path = ops
    assert store.migrations_are_current()
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"DROP {'TABLE' if missing == 'automation_operation_receipts' else 'TRIGGER'} {missing}"
        )
    assert not store.migrations_are_current()


@pytest.mark.parametrize("provider", ["meta", "twilio"])
def test_legacy_messages_keep_unresumed_behavior_but_require_source_time_after_resume(
    ops, provider
):
    from rj_studio_ai.domain import InboundMessage

    store, _, _ = ops
    message = InboundMessage(provider, "legacy", "synthetic-customer", "studio", "Synthetic")
    claim = store.claim_generation(message)
    assert claim.acquired
    opaque = store.automation_identifier(claim.inbound_message_id)
    store.change_automation(opaque, "pause", uuid4().hex, 0, "operator-test")
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    assert (
        store.claim_generation(replace(message, provider_message_id="late")).state
        is GenerationState.SUPPRESSED
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"operation_id": "0" * 32, "expected_revision": True},
        {"operation_id": "0" * 32, "expected_revision": 2**64},
        {"operation_id": "invalid", "expected_revision": 0},
        {"operation_id": "0" * 32, "expected_revision": -1},
    ],
)
def test_invalid_commands_are_redacted_and_have_no_effect(ops, payload):
    store, opaque, _ = ops
    response = api(store).post(
        f"/admin/conversations/{opaque}/automation/pause",
        headers={"Authorization": f"Bearer {SECRET}"},
        json=payload,
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_operation"}
    assert store.get_automation_state(opaque)["revision"] == 0


def test_configuration_repr_dump_and_errors_hide_digest():
    from pydantic import ValidationError

    digest = hashlib.sha256(SECRET.encode()).hexdigest()
    settings = Settings(_env_file=None, operator_secret_sha256=digest)
    assert digest not in repr(settings) + str(settings.model_dump())
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, operator_secret_sha256={"private": SECRET})
    assert SECRET not in str(error.value)


@pytest.mark.parametrize("interrupt", [False, True])
def test_migration_preserves_ticket04_evidence_and_rolls_back_atomically(
    tmp_path, monkeypatch, interrupt
):
    from alembic import command
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from rj_studio_ai.migrations import MigrationManager

    path = tmp_path / "legacy.db"
    upgrade = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command, "upgrade", lambda config, _: upgrade(config, "0016_operational_outbound_fence")
        )
        MigrationManager(path).upgrade()
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO conversations VALUES (1,'synthetic','customer',?,?)",
            (NOW.isoformat(), NOW.isoformat()),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id,provider,provider_message_id,"
            "recipient_address,direction,body,created_at) "
            "VALUES (1,'synthetic','message-customer','studio','inbound','Synthetic',?)",
            (NOW.isoformat(),),
        )
    store = SqliteConversationStore(path)
    store.record_webhook_events((human(),), now=NOW)
    tables = (
        "conversations",
        "messages",
        "message_processing",
        "human_pause_effects",
        "operational_events",
    )
    from test_operational_event_journal import rows

    before = {t: rows(path, t) for t in tables}

    def fault(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE automation_operation_receipts" in statement:
            raise RuntimeError("synthetic interruption")

    if interrupt:
        event.listen(Engine, "after_cursor_execute", fault)
    try:
        if interrupt:
            with pytest.raises(RuntimeError, match="synthetic interruption"):
                MigrationManager(path).upgrade()
        else:
            MigrationManager(path).upgrade()
    finally:
        if interrupt:
            event.remove(Engine, "after_cursor_execute", fault)
    if interrupt:
        with sqlite3.connect(path) as conn:
            assert (
                conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "0016_operational_outbound_fence"
            )
            assert "resumed_at" not in {
                r[1] for r in conn.execute("PRAGMA table_info(conversation_automation_controls)")
            }
            assert not conn.execute(
                "SELECT name FROM sqlite_master WHERE name='conversation_operation_ids'"
            ).fetchall()
        MigrationManager(path).upgrade()
    for t, values in before.items():
        assert rows(path, t) == values
    assert store.migrations_are_current()
    opaque = store.automation_identifier(1)
    assert store.get_automation_state(opaque)["paused"]
    store.change_automation(opaque, "resume", uuid4().hex, 1, "operator-test")
    reopened = SqliteConversationStore(path)
    reopened.initialize()
    assert reopened.automation_identifier(1) == opaque
    assert reopened.get_automation_state(opaque)["revision"] == 2
