"""Outbound pause boundaries with temporary SQLite and synthetic, in-process senders."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest
from alembic import command
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import Engine
from test_coexistence_contracts import NOW, human, inbound
from test_generation_pause import controls, pause
from test_human_handoff import _activate
from test_operational_event_journal import identified, rows

from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import DeliveryStatus, DeliveryStatusReceived
from rj_studio_ai.migrations import MigrationManager
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import (
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "outbound-pause.db"
    store = SqliteConversationStore(path)
    store.initialize()
    return store, path


def pending(store, message=None, state=DeliveryState.PENDING):
    claim = store.claim_generation(message or inbound(), now=NOW)
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="Synthetic private reply",
        delivery_state=state,
        now=NOW,
    )
    return store.get_delivery_for_inbound(claim.inbound_message_id)


def authorize(store, claim, now=NOW):
    return store.authorize_delivery_submission(
        delivery_id=claim.delivery_id, owner_token=claim.owner_token, now=now
    )


def delivery_runner(store, sender=None):
    return OutboundDeliveryRunner(
        store, sender or DeterministicFakeOutboundSender(outcomes=[]), timeout_seconds=1
    )


def finished(store, claim, state, **kwargs):
    return store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=state,
        now=NOW,
        **kwargs,
    )


@pytest.mark.parametrize("state", ["pending", "retryable", "sending", "expired_unsubmitted"])
def test_pause_cancels_only_proven_unsubmitted_and_preserves_history(db, state):
    store, path = db
    delivery = pending(store)
    if state != "pending":
        claim = store.claim_next_delivery(now=NOW)
        if state == "retryable":
            assert authorize(store, claim)
            assert finished(
                store,
                claim,
                DeliveryState.RETRYABLE,
                safe_error_code="provider_retryable",
                retry_at=NOW + timedelta(seconds=1),
            )
    messages = rows(path, "messages")
    metrics = store.get_delivery_metric(delivery.delivery_id)
    attempts = rows(path, "delivery_attempts")
    pause(store, now=NOW + timedelta(seconds=60 if state == "expired_unsubmitted" else 0))
    cancelled = store.get_delivery(delivery.delivery_id)
    assert cancelled.state is DeliveryState.CANCELLED
    assert cancelled.owner_token is cancelled.lease_expires_at is cancelled.next_attempt_at is None
    assert cancelled.safe_error_code == "operational_pause_cancelled"
    assert cancelled.attempt_count == len(attempts)
    assert rows(path, "messages") == messages
    assert store.get_delivery_metric(delivery.delivery_id).attempt_count == metrics.attempt_count
    assert store.get_delivery_metric(delivery.delivery_id).acceptance_latency_ms is None
    if state == "retryable":
        assert rows(path, "delivery_attempts") == attempts
    elif attempts:
        attempt = rows(path, "delivery_attempts")[0]
        assert attempt["outcome"] == "failed"
        assert attempt["safe_error_code"] == "operational_pause_cancelled"
        assert attempt["owner_token"] == attempts[0]["owner_token"]
        assert not authorize(store, claim)
        assert not store.delivery_claim_is_current(
            delivery_id=claim.delivery_id, owner_token=claim.owner_token, now=NOW
        )
        assert not finished(store, claim, DeliveryState.ACCEPTED, provider_message_id="too-late")
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert delivery_runner(restarted).run_once(now=NOW + timedelta(days=5)) is None
    assert restarted.get_delivery(delivery.delivery_id).state is DeliveryState.CANCELLED


@pytest.mark.parametrize("state", [DeliveryState.UNKNOWN, DeliveryState.ACCEPTED_LEGACY])
@pytest.mark.parametrize("legacy_authorized", [False, True])
def test_legacy_states_preserved_but_render_authorization_blocked(db, state, legacy_authorized):
    store, path = db
    delivery = pending(store, state=state)
    if legacy_authorized:
        assert store.authorize_legacy_reply(delivery_id=delivery.delivery_id)
    before = rows(path, "outbound_deliveries")
    pause(store)
    assert rows(path, "outbound_deliveries") == before
    assert not store.authorize_legacy_reply(delivery_id=delivery.delivery_id)
    assert delivery_runner(store).run_once(now=NOW) is None


@pytest.mark.parametrize(
    "state", ["sending", "unknown", "accepted", "sent", "delivered", "read", "failed"]
)
def test_pause_preserves_possible_submission_and_external_evidence(db, state):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    assert authorize(store, claim)
    if state != "sending":
        outcome = (
            DeliveryState.ACCEPTED
            if state in {"accepted", "sent", "delivered", "read"}
            else DeliveryState(state)
        )
        assert finished(
            store,
            claim,
            outcome,
            provider_message_id="provider-result" if outcome is DeliveryState.ACCEPTED else None,
            safe_error_code="synthetic_outcome" if outcome is not DeliveryState.ACCEPTED else None,
        )
        if state in {"sent", "delivered", "read"}:
            store.record_delivery_status(
                DeliveryStatusReceived("synthetic", "provider-result", DeliveryStatus(state))
            )
    before = rows(path, "outbound_deliveries")
    attempts = rows(path, "delivery_attempts")
    pause(store)
    assert rows(path, "outbound_deliveries") == before
    assert rows(path, "delivery_attempts") == attempts
    assert not authorize(store, claim)
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert delivery_runner(restarted).run_once(now=NOW + timedelta(days=5)) is None
    assert restarted.get_delivery(claim.delivery_id).state.value == (
        "unknown" if state == "sending" else state
    )


def test_runner_pause_between_claim_and_authorization_never_calls_sender(db, monkeypatch):
    store, path = db
    pending(store)
    original = store.authorize_delivery_submission

    def pausing(**kwargs):
        pause(SqliteConversationStore(path))
        return original(**kwargs)

    monkeypatch.setattr(store, "authorize_delivery_submission", pausing)
    sender = DeterministicFakeOutboundSender(outcomes=[])
    assert delivery_runner(store, sender).run_once(now=NOW).state is DeliveryState.CANCELLED
    assert sender.calls == []


@pytest.mark.parametrize("pause_first", [False, True])
def test_pause_and_authorization_have_serial_commit_orders(db, monkeypatch, pause_first):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    entered, release, contender = Event(), Event(), Event()
    original = store._connect
    needle = (
        "INSERT INTO human_pause_effects"
        if pause_first
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

    def second():
        contender.set()
        return authorize(other, claim) if pause_first else pause(other)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(pause, store) if pause_first else pool.submit(authorize, store, claim)
        try:
            assert entered.wait(timeout=5)
            next_result = pool.submit(second)
            assert contender.wait(timeout=5)
        finally:
            release.set()
        first_result, second_result = first.result(timeout=5), next_result.result(timeout=5)
    assert (second_result if pause_first else first_result) is (not pause_first)
    record = store.get_delivery(claim.delivery_id)
    assert record.state is (DeliveryState.CANCELLED if pause_first else DeliveryState.SENDING)
    assert (rows(path, "outbound_deliveries")[0]["submission_started_at"] is None) is pause_first
    assert controls(path)[0]["paused"] == 1
    assert not authorize(other, claim)


@pytest.mark.parametrize(
    "outcome,expected,attempt_outcome",
    [
        (ProviderAcceptance("synthetic-acceptance"), DeliveryState.ACCEPTED, "accepted"),
        (OutboundOutcomeUnknown("synthetic"), DeliveryState.UNKNOWN, "unknown"),
        (OutboundPermanentError("synthetic"), DeliveryState.FAILED, "failed"),
        (OutboundRetryableError("synthetic"), DeliveryState.CANCELLED, "retryable"),
    ],
)
def test_pause_during_io_preserves_late_result_and_retry_evidence(
    db, outcome, expected, attempt_outcome
):
    store, path = db
    pending(store)
    fake = DeterministicFakeOutboundSender(outcomes=[outcome])

    class PausingSender:
        def send(self, message, *, timeout_seconds):
            # Another connection can commit while sender I/O is in progress.
            pause(SqliteConversationStore(path))
            return fake.send(message, timeout_seconds=timeout_seconds)

    assert delivery_runner(store, PausingSender()).run_once(now=NOW).state is expected
    assert len(fake.calls) == 1
    attempt = rows(path, "delivery_attempts")[0]
    assert attempt["outcome"] == attempt_outcome
    if attempt_outcome == "retryable":
        assert attempt["safe_error_code"] == "provider_retryable"
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert delivery_runner(restarted, fake).run_once(now=NOW + timedelta(days=1)) is None
    assert len(fake.calls) == 1


def test_pause_after_authorization_before_http_exposes_documented_residual_window(db, monkeypatch):
    store, path = db
    pending(store)
    original = store.authorize_delivery_submission

    def authorized_then_paused(**kwargs):
        result = original(**kwargs)
        assert result
        pause(SqliteConversationStore(path))
        return result

    monkeypatch.setattr(store, "authorize_delivery_submission", authorized_then_paused)
    fake = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("window-result")])
    assert delivery_runner(store, fake).run_once(now=NOW).state is DeliveryState.ACCEPTED
    assert (
        len(fake.calls) == 1
    )  # No claim of external exactly-once or retracting already-authorized I/O.
    assert delivery_runner(SqliteConversationStore(path), fake).run_once(now=NOW) is None


@pytest.mark.parametrize("boundary", ["claim", "authorized", "remote_accepted", "finalized"])
def test_restart_at_submission_boundaries_never_replays(db, boundary):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    fake = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("crash-result")])
    if boundary != "claim":
        assert authorize(store, claim)
    if boundary in {"remote_accepted", "finalized"}:
        from rj_studio_ai.domain import OutboundMessage

        result = fake.send(OutboundMessage("studio", "customer", "Synthetic"), timeout_seconds=1)
        if boundary == "finalized":
            assert finished(
                store, claim, DeliveryState.ACCEPTED, provider_message_id=result.provider_message_id
            )
    # Simulate process loss: discard the owner work item, reopen storage.
    reopened = SqliteConversationStore(path)
    reopened.initialize()
    pause(reopened)
    assert delivery_runner(reopened, fake).run_once(now=NOW + timedelta(seconds=60)) is None
    expected = {"claim": DeliveryState.CANCELLED, "finalized": DeliveryState.ACCEPTED}.get(
        boundary, DeliveryState.UNKNOWN
    )
    assert reopened.get_delivery(claim.delivery_id).state is expected
    assert len(fake.calls) == (1 if boundary in {"remote_accepted", "finalized"} else 0)


def test_expiration_before_pause_remains_unknown_even_without_submission_marker(db):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    assert store.claim_next_delivery(now=NOW + timedelta(seconds=60)) is None
    before = rows(path, "outbound_deliveries")
    pause(store)
    assert rows(path, "outbound_deliveries") == before
    assert store.get_delivery(claim.delivery_id).state is DeliveryState.UNKNOWN


def test_duplicate_pause_and_envelope_preserve_cancellation_and_attempt_receipts(db):
    store, path = db
    pending(store)
    store.claim_next_delivery(now=NOW)
    pause(store)
    before = {
        table: rows(path, table)
        for table in (
            "outbound_deliveries",
            "delivery_attempts",
            "human_pause_effects",
            "conversation_automation_controls",
        )
    }
    for event in (human(), identified(human(), "second-envelope")):
        pause(store, event, now=NOW + timedelta(days=2))
    for table, values in before.items():
        assert rows(path, table) == values
    assert len(rows(path)) == 2
    assert delivery_runner(store).run_once(now=NOW) is None


@pytest.mark.parametrize("claimed", [False, True])
def test_handoff_confirmation_cancelled_by_human_and_release_cannot_revive(db, claimed):
    store, path = db
    generation, handoff = _activate(store, message=inbound(), now=NOW)
    if claimed:
        claim = store.claim_next_delivery(now=NOW)
        assert claim.handoff_token == handoff.owner_token
    pause(store)
    delivery = store.get_delivery_for_inbound(generation.inbound_message_id)
    assert delivery.state is DeliveryState.CANCELLED
    assert store.list_active_handoffs() == [handoff]
    suppressed = store.admit_generation(
        replace(inbound(), provider_message_id="suppressed"), now=NOW
    )
    assert suppressed.state is GenerationState.SUPPRESSED
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token, now=NOW
    )
    assert store.list_pending_generations(now=NOW) == []
    assert delivery_runner(store).run_once(now=NOW) is None
    assert rows(path, "outbound_deliveries")[0]["state"] == "cancelled"


def test_unpaused_handoff_confirmation_is_still_permitted(db):
    store, _ = db
    _activate(store, message=inbound(), now=NOW)
    fake = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("confirmation")])
    assert delivery_runner(store, fake).run_once(now=NOW).state is DeliveryState.ACCEPTED
    assert len(fake.calls) == 1


def test_handoff_release_does_not_cancel_legacy_unknown_when_operationally_paused(db):
    store, path = db
    generation = store.claim_generation(inbound(), now=NOW)
    assert store.complete_generation(
        inbound_message_id=generation.inbound_message_id,
        owner_token=generation.owner_token,
        reply_body="Synthetic confirmation",
        delivery_state=DeliveryState.UNKNOWN,
        handoff_reason="explicit_human_request",
        now=NOW,
    )
    handoff = store.list_active_handoffs()[0]
    pause(store)
    before = rows(path, "outbound_deliveries")
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token, now=NOW
    )
    assert rows(path, "outbound_deliveries") == before
    assert not store.authorize_legacy_reply(delivery_id=before[0]["id"])


@pytest.mark.parametrize(
    "statuses",
    [
        (DeliveryStatus.READ, DeliveryStatus.DELIVERED, DeliveryStatus.SENT),
        (DeliveryStatus.SENT, DeliveryStatus.DELIVERED, DeliveryStatus.READ),
    ],
)
def test_early_out_of_order_statuses_merge_with_acceptance_after_pause(db, statuses):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    assert authorize(store, claim)
    for status in statuses:
        store.record_delivery_status(
            DeliveryStatusReceived("synthetic", "early-result", status), now=NOW
        )
    pause(store)
    assert finished(store, claim, DeliveryState.ACCEPTED, provider_message_id="early-result")
    assert store.get_delivery(claim.delivery_id).state is DeliveryState.READ
    assert rows(path, "delivery_attempts")[0]["outcome"] == "accepted"
    assert rows(path, "pending_delivery_statuses") == []


def test_two_conversations_run_in_parallel_only_paused_one_is_blocked(db, monkeypatch):
    store, path = db
    pending(store)
    pending(
        store, replace(inbound(), customer_address="other-customer", provider_message_id="other")
    )
    entered, release = Event(), Event()
    original = store.authorize_delivery_submission

    def wait_before_authorizing(**kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(store, "authorize_delivery_submission", wait_before_authorizing)
    fake_a = DeterministicFakeOutboundSender(outcomes=[])
    fake_b = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("other-result")])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(delivery_runner(store, fake_a).run_once, now=NOW)
        try:
            assert entered.wait(timeout=5)
            second = pool.submit(
                delivery_runner(SqliteConversationStore(path), fake_b).run_once, now=NOW
            )
            assert second.result(timeout=5).state is DeliveryState.ACCEPTED
            pause(SqliteConversationStore(path))
        finally:
            release.set()
        assert first.result(timeout=5).state is DeliveryState.CANCELLED
    assert fake_a.calls == [] and len(fake_b.calls) == 1


@pytest.mark.parametrize("failure", ["invalid_batch", "effect", "commit"])
def test_pause_batch_rollback_restores_outbox_owner_attempts_and_journal(
    db, monkeypatch, caplog, failure
):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    tables = ("messages", "outbound_deliveries", "delivery_attempts", "message_processing")
    before = {table: rows(path, table) for table in tables}
    events = (human(), replace(inbound(), provider_message_id="mixed-new"))
    if failure == "invalid_batch":
        events += (object(),)
    elif failure == "effect":
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TRIGGER fail_effect BEFORE INSERT ON human_pause_effects "
                "BEGIN SELECT RAISE(ABORT, 'PRIVATE-FAILURE'); END"
            )
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
    assert "PRIVATE-FAILURE" not in str(caught.value) + caplog.text
    assert "Synthetic private reply" not in caplog.text
    for table, values in before.items():
        assert rows(path, table) == values
    assert controls(path) == rows(path) == rows(path, "human_pause_effects") == []
    monkeypatch.undo()
    assert authorize(store, claim)


@pytest.mark.parametrize("interrupt", [False, True])
def test_migration_backfills_existing_pauses_atomically_without_replaying_effects(
    tmp_path, monkeypatch, interrupt
):
    path = tmp_path / "ticket03.db"
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(
            command,
            "upgrade",
            lambda config, _: original(config, "0015_operational_generation_pause"),
        )
        MigrationManager(path).upgrade()
    store = SqliteConversationStore(path)
    delivery = pending(store)
    claim = store.claim_next_delivery(now=NOW)
    pause(store)
    before_controls, before_effects = controls(path), rows(path, "human_pause_effects")
    before_outbox, before_attempts = (
        rows(path, "outbound_deliveries"),
        rows(path, "delivery_attempts"),
    )
    assert before_outbox[0]["state"] == "sending"  # Ticket 03 did not fence outbound.

    def fault(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE delivery_attempts SET outcome"):
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
    assert controls(path) == before_controls
    assert rows(path, "human_pause_effects") == before_effects
    if interrupt:
        assert rows(path, "outbound_deliveries") == before_outbox
        assert rows(path, "delivery_attempts") == before_attempts
        with sqlite3.connect(path) as connection:
            assert (
                connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == "0015_operational_generation_pause"
            )
            assert not connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name LIKE 'operational_pause_cancels_outbound%'"
            ).fetchall()
        MigrationManager(path).upgrade()
    assert store.get_delivery(delivery.delivery_id).state is DeliveryState.CANCELLED
    assert rows(path, "delivery_attempts")[0]["safe_error_code"] == "operational_pause_cancelled"
    assert not authorize(store, claim)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    store.initialize()
    assert controls(path) == before_controls


@pytest.mark.parametrize(
    "missing",
    [
        "operational_pause_cancels_outbound_insert",
        "operational_pause_cancels_outbound_update",
        "operational_pause_cancels_ready_delivery_insert",
        "operational_pause_cancels_ready_delivery_update",
        "operational_pause_rejects_delivery_authorization",
    ],
)
def test_readiness_requires_outbound_pause_guards(db, missing):
    store, path = db
    assert store.migrations_are_current()
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP TRIGGER {missing}")
    assert not store.migrations_are_current()


@pytest.mark.parametrize("provider", ["meta", "twilio"])
def test_provider_neutral_pause_cancels_legacy_inbound_reply(db, provider):
    from rj_studio_ai.domain import InboundMessage

    store, _ = db
    legacy = InboundMessage(provider, "legacy-inbound", "customer", "studio", "Synthetic")
    delivery = pending(store, legacy)
    pause(store, replace(human(), provider=provider))
    assert store.get_delivery(delivery.delivery_id).state is DeliveryState.CANCELLED
    assert delivery_runner(store).run_once(now=NOW) is None


@pytest.mark.parametrize("invalid", ["owner", "expired", "already_authorized"])
def test_authorization_still_checks_owner_lease_and_one_shot_marker(db, invalid):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    if invalid == "already_authorized":
        assert authorize(store, claim)
    before = rows(path, "outbound_deliveries")
    owner = "stale-owner" if invalid == "owner" else claim.owner_token
    now = NOW + timedelta(seconds=60) if invalid == "expired" else NOW
    assert not store.authorize_delivery_submission(
        delivery_id=claim.delivery_id, owner_token=owner, now=now
    )
    assert rows(path, "outbound_deliveries") == before


def test_two_workers_cannot_claim_or_authorize_duplicate_delivery(db):
    store, path = db
    pending(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(lambda _: SqliteConversationStore(path).claim_next_delivery(now=NOW), range(2))
        )
    acquired = [claim for claim in claims if claim is not None]
    assert len(acquired) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: authorize(SqliteConversationStore(path), acquired[0]), range(2))
        )
    assert sorted(results) == [False, True]
    assert len(rows(path, "delivery_attempts")) == 1
    pause(store)
    assert not authorize(store, acquired[0])


def test_failed_authorization_commit_leaves_no_submission_evidence(db, monkeypatch):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    before = rows(path, "outbound_deliveries")
    original = store._connect

    @contextmanager
    def fail_commit(*args, **kwargs):
        with original(*args, **kwargs) as connection:
            connection.execute("PRAGMA defer_foreign_keys = ON")
            yield connection
            if connection.in_transaction:
                connection.execute("INSERT INTO operational_event_aliases VALUES (-1, 'ns', 'id')")

    monkeypatch.setattr(store, "_connect", fail_commit)
    with pytest.raises(PersistenceUnavailable):
        authorize(store, claim)
    assert rows(path, "outbound_deliveries") == before
    monkeypatch.undo()
    pause(SqliteConversationStore(path))
    assert store.get_delivery(claim.delivery_id).state is DeliveryState.CANCELLED


def test_valid_mixed_batch_commits_pause_cancellation_status_and_suppression(db):
    store, path = db
    first = pending(store)
    other_message = replace(
        inbound(), customer_address="other-customer", provider_message_id="other"
    )
    second = pending(store, other_message)
    store.record_webhook_events(
        (
            DeliveryStatusReceived("synthetic", "early-mixed", DeliveryStatus.READ),
            human(),
            replace(inbound(), provider_message_id="new-paused"),
            replace(other_message, provider_message_id="new-other"),
        ),
        now=NOW,
    )
    assert store.get_delivery(first.delivery_id).state is DeliveryState.CANCELLED
    assert store.get_delivery(second.delivery_id).state is DeliveryState.PENDING
    assert len(rows(path, "pending_delivery_statuses")) == 1
    assert len(controls(path)) == len(rows(path, "human_pause_effects")) == 1
    assert (
        store.get_generation(provider="synthetic", provider_message_id="new-paused").state
        is GenerationState.SUPPRESSED
    )
    assert (
        store.get_generation(provider="synthetic", provider_message_id="new-other").state
        is GenerationState.RETRYABLE
    )


def test_database_guard_rejects_legacy_marker_bypass_while_paused(db):
    store, path = db
    delivery = pending(store, state=DeliveryState.UNKNOWN)
    pause(store)
    with (
        sqlite3.connect(path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="operational pause rejects"),
    ):
        connection.execute(
            "UPDATE outbound_deliveries SET submission_started_at=? WHERE id=?",
            (NOW.isoformat(), delivery.delivery_id),
        )
    assert store.get_delivery(delivery.delivery_id).state is DeliveryState.UNKNOWN


def test_submission_lease_expiry_and_late_acceptance_remain_conservative(db):
    store, path = db
    pending(store)
    claim = store.claim_next_delivery(now=NOW)
    assert authorize(store, claim)
    pause(store)
    restarted = SqliteConversationStore(path)
    restarted.initialize()
    assert restarted.claim_next_delivery(now=NOW + timedelta(seconds=60)) is None
    assert not restarted.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="late-expired",
        now=NOW + timedelta(seconds=60),
    )
    assert restarted.get_delivery(claim.delivery_id).state is DeliveryState.UNKNOWN
    assert rows(path, "delivery_attempts")[0]["safe_error_code"] == "sending_lease_expired"
