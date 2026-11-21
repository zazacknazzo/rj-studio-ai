"""Ticket 10: synthetic policy evidence with real SQLite and no external sender."""

import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from threading import Barrier
from uuid import UUID

import pytest
from telnyx_channel_fixture import verified_consent
from test_generation_pause import complete
from test_telnyx_authentication import PHONE, PRIVATE_TEXT, signed
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_delivery_status import pending, status_wire
from test_telnyx_lifecycle import account
from test_telnyx_messages import CUSTOMER, TIME, receive, wire
from test_telnyx_messages import ingress as ingress

from rj_studio_ai.delivery import DeliveryOwnershipLost, OutboundDeliveryRunner
from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import OutboundRetryableError, ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.telnyx_submission import RetryEvidence
from rj_studio_ai.whatsapp_policy import EligibilityKind


def prepare(ingress, *, now=TIME):
    _, store, path = ingress
    pending(store)
    claim = store.claim_next_delivery(now=now)
    assert claim is not None
    return store, path, claim


def outbound(claim):
    return OutboundMessage(
        claim.provider_channel_id,
        claim.recipient_address,
        claim.body,
        submission_key=claim.submission_key,
    )


def assess(store, claim, *, now=TIME, message=None):
    return store.assess_telnyx_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=message,
        now=now,
    )


def authorize(store, claim, *, now=TIME, message=None):
    return store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=message or outbound(claim),
        now=now,
    )


@pytest.mark.parametrize(
    "offset,allowed",
    [(timedelta(microseconds=-1), True), (timedelta(0), False), (timedelta(microseconds=1), False)],
)
def test_exact_window_boundary(ingress, offset, allowed):
    store, path, claim = prepare(ingress)
    source = TIME - timedelta(hours=24) - offset
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE inbound_event_receipts SET message_occurred_at=?", (source.isoformat(),)
        )
    assert assess(store, claim).eligible is allowed
    assert authorize(store, claim) is allowed


@pytest.mark.parametrize(
    "column,value",
    [
        ("message_occurred_at", None),
        ("message_occurred_at", "invalid"),
        ("message_occurred_at", TIME.replace(tzinfo=None).isoformat()),
        ("occurred_at", "invalid"),
        ("received_at", "invalid"),
        ("message_occurred_at", (TIME + timedelta(seconds=1)).isoformat()),
        ("occurred_at", (TIME + timedelta(seconds=1)).isoformat()),
        ("received_at", (TIME + timedelta(seconds=1)).isoformat()),
    ],
)
def test_invalid_or_future_receipt_cannot_authorize(ingress, column, value):
    store, path, claim = prepare(ingress)
    with sqlite3.connect(path) as connection:
        connection.execute(f"UPDATE inbound_event_receipts SET {column}=?", (value,))
    assert not authorize(store, claim)
    assert store.get_delivery(claim.delivery_id).first_submission_at is None


def test_later_replay_does_not_rehabilitate_first_future_receipt(ingress):
    store, path, claim = prepare(ingress)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE inbound_event_receipts SET occurred_at=?",
            ((TIME + timedelta(seconds=1)).isoformat(),),
        )
        connection.execute(
            "INSERT INTO inbound_event_receipts(provider,channel_id,customer_address,event_id,"
            "provider_message_id,occurred_at,message_occurred_at,aliases_json,received_at) "
            "SELECT provider,channel_id,customer_address,'second-envelope',provider_message_id,"
            "?,message_occurred_at,aliases_json,? FROM inbound_event_receipts",
            (TIME.isoformat(), TIME.isoformat()),
        )
    assert not authorize(store, claim, now=TIME + timedelta(seconds=2))


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM telnyx_consent",
        "UPDATE telnyx_consent SET revoked_at='invalid'",
        "UPDATE telnyx_consent SET expires_at='2000-01-01T00:00:00+00:00'",
    ],
)
def test_consent_missing_revoked_or_expired(ingress, mutation):
    store, path, claim = prepare(ingress)
    with sqlite3.connect(path) as connection:
        connection.execute(mutation)
    assert assess(store, claim).decision.reason == "consent_unproven"
    assert not authorize(store, claim)


def test_clock_highwater_persists_denial_and_survives_restart(ingress):
    store, path, claim = prepare(ingress)
    future = TIME + timedelta(days=1)
    assert not assess(store, claim, now=future).eligible
    restarted = SqliteConversationStore(path)
    assert assess(restarted, claim).decision.reason == "clock_unproven"
    assert not authorize(restarted, claim)


def test_stable_key_retry_restart_and_new_delivery(ingress):
    store, path, first = prepare(ingress)
    assert UUID(first.submission_key).version == 4
    assert store.finalize_delivery(
        delivery_id=first.delivery_id,
        owner_token=first.owner_token,
        outcome=DeliveryState.RETRYABLE,
        retry_evidence=RetryEvidence.NOT_SUBMITTED,
        safe_error_code="local_not_submitted",
        retry_at=TIME + timedelta(seconds=1),
        now=TIME,
    )
    restarted = SqliteConversationStore(path)
    second = restarted.claim_next_delivery(now=TIME + timedelta(seconds=1))
    assert second.submission_key == first.submission_key
    assert second.owner_token != first.owner_token
    assert second.attempt_count == 2
    assert authorize(restarted, second, now=TIME + timedelta(seconds=1))
    assert not authorize(restarted, second, now=TIME + timedelta(seconds=1))
    assert restarted.finalize_delivery(
        delivery_id=second.delivery_id,
        owner_token=second.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="synthetic-acceptance",
        now=TIME + timedelta(seconds=1),
    )
    pending(restarted, message_id="second-logical")
    third = restarted.claim_next_delivery(now=TIME + timedelta(seconds=2))
    assert third.submission_key != first.submission_key
    attempts = restarted.get_delivery_attempts(first.delivery_id)
    assert attempts[0].retry_evidence == "not_submitted"
    assert attempts[0].submission_started_at is None
    assert attempts[1].submission_started_at == TIME + timedelta(seconds=1)
    assert (
        restarted.get_delivery(first.delivery_id).first_submission_at
        == attempts[1].submission_started_at
    )


@pytest.mark.parametrize(
    "marker,proof", [(False, None), (True, None), (True, RetryEvidence.NOT_SUBMITTED)]
)
def test_unproven_or_possible_submission_never_retries(ingress, marker, proof):
    store, path, claim = prepare(ingress)
    if marker:
        assert authorize(store, claim)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.RETRYABLE,
        retry_evidence=proof,
        safe_error_code="synthetic_timeout",
        retry_at=TIME + timedelta(seconds=1),
        now=TIME,
    )
    restarted = SqliteConversationStore(path)
    assert restarted.get_delivery(claim.delivery_id).state is DeliveryState.UNKNOWN
    assert restarted.claim_next_delivery(now=TIME + timedelta(days=2)) is None
    assert not authorize(restarted, claim, now=TIME + timedelta(days=2))


@pytest.mark.parametrize("marker", [False, True])
def test_crash_expired_claim_is_unknown(ingress, marker):
    store, path, claim = prepare(ingress)
    if marker:
        assert authorize(store, claim)
    restarted = SqliteConversationStore(path)
    assert restarted.claim_next_delivery(now=TIME + timedelta(seconds=31)) is None
    assert restarted.get_delivery(claim.delivery_id).state is DeliveryState.UNKNOWN
    assert not authorize(restarted, claim, now=TIME + timedelta(seconds=31))


@pytest.mark.parametrize(
    "change",
    [
        dict(body="changed"),
        dict(recipient_address="+5511999999999"),
        dict(submission_key="00000000-0000-4000-8000-000000000000"),
    ],
)
def test_claim_payload_or_key_collision_denies(ingress, change):
    store, _, claim = prepare(ingress)
    message = replace(outbound(claim), **change)
    assert assess(store, claim, message=message).decision.reason == "key_payload_conflict"
    assert not authorize(store, claim, message=message)


def test_identity_and_body_sql_guards(ingress):
    store, path, claim = prepare(ingress)
    with sqlite3.connect(path) as connection:
        for sql in (
            "UPDATE outbound_deliveries SET submission_key='replacement'",
            "UPDATE outbound_deliveries SET payload_fingerprint='replacement'",
            "UPDATE messages SET body='replacement' WHERE direction='outbound'",
            "INSERT OR REPLACE INTO outbound_deliveries SELECT * FROM outbound_deliveries",
            "INSERT OR REPLACE INTO messages SELECT * FROM messages WHERE direction='outbound'",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql)
    assert authorize(store, claim)


def test_concurrent_authorization_is_single_use(ingress):
    store, path, claim = prepare(ingress)
    barrier = Barrier(2)

    def submit():
        peer = SqliteConversationStore(path)
        barrier.wait()
        return authorize(peer, claim)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(results) == [False, True]
    assert store.get_delivery_attempts(claim.delivery_id)[0].submission_started_at == TIME


def test_sqlite_failure_rolls_back_all_submission_evidence(ingress, monkeypatch):
    store, path, claim = prepare(ingress)
    original = store._connect

    @contextmanager
    def failure(*args):
        with original(*args) as connection:
            connection.execute(
                "CREATE TEMP TRIGGER fail_marker BEFORE UPDATE OF first_submission_at "
                "ON outbound_deliveries BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
            )
            yield connection

    monkeypatch.setattr(store, "_connect", failure)
    with pytest.raises(PersistenceUnavailable):
        authorize(store, claim)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT submission_started_at,first_submission_at FROM outbound_deliveries"
        ).fetchone() == (None, None)
        assert connection.execute(
            "SELECT submission_started_at FROM delivery_attempts"
        ).fetchone() == (None,)
        assert connection.execute("SELECT * FROM telnyx_policy_clock").fetchall() == []
    monkeypatch.setattr(store, "_connect", original)
    assert authorize(store, claim)


def test_assessment_rechecks_revocation_before_authorization(ingress):
    store, path, claim = prepare(ingress)
    assert assess(store, claim).eligible
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))
    assert not authorize(store, claim)


def test_unknown_assessment_and_telnyx_legacy_denial(ingress):
    store, _, claim = prepare(ingress)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.UNKNOWN,
        safe_error_code="synthetic_unknown",
        now=TIME,
    )
    assert assess(store, claim).decision.kind is EligibilityKind.OPERATIONAL_UNKNOWN
    assert not store.authorize_legacy_reply(delivery_id=claim.delivery_id)


@pytest.mark.parametrize("kind", ["status", "echo", "edit", "revoke", "reconnect"])
def test_operational_events_never_create_window_evidence(ingress, private_key, kind):
    store, path, claim = prepare(ingress)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM inbound_event_receipts")
    payload = (
        status_wire()
        if kind == "status"
        else account("ACCOUNT_RECONNECTED")
        if kind == "reconnect"
        else wire(kind)
    )
    receive(ingress, private_key, payload)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM inbound_event_receipts").fetchall() == []
    result = assess(store, claim)
    assert not result.eligible
    if kind in {"status", "edit", "revoke"}:
        assert result.decision.reason == "customer_window_unproven"
    elif kind == "reconnect":
        assert result.decision.kind is EligibilityKind.CHANNEL_BLOCKED
    assert not authorize(store, claim)


@pytest.mark.parametrize("age,allowed", [(timedelta(hours=23), True), (timedelta(hours=24), False)])
def test_signed_customer_replay_preserves_first_window_evidence(ingress, private_key, age, allowed):
    adapter, store, path = ingress
    payload = wire()
    receive(ingress, private_key, payload)
    generation = store.claim_generation(
        adapter.receive(signed(private_key, payload)).events[0], now=TIME
    )
    assert complete(store, generation, now=TIME)
    with sqlite3.connect(path) as connection:
        original = connection.execute("SELECT * FROM inbound_event_receipts").fetchall()
    receive(ingress, private_key, payload, now=TIME + age)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT * FROM inbound_event_receipts").fetchall() == original
    claim = store.claim_next_delivery(now=TIME + age)
    assert authorize(store, claim, now=TIME + age) is allowed


def test_bsuid_without_sender_identity_contract_is_denied(ingress):
    _, store, path = ingress
    customer = "bsuid:synthetic-hidden-customer"
    verified_consent(path, customer=customer, now=TIME)
    pending(store, customer=customer)
    claim = store.claim_next_delivery(now=TIME)
    assert assess(store, claim).decision.reason == "recipient_unproven"
    assert not authorize(store, claim)


def test_attempt_and_clock_evidence_cannot_be_rewritten(ingress):
    store, path, claim = prepare(ingress)
    assert authorize(store, claim)
    with sqlite3.connect(path) as connection:
        for statement in (
            "UPDATE outbound_deliveries SET first_submission_at=NULL",
            "UPDATE delivery_attempts SET submission_started_at=NULL",
            "UPDATE delivery_attempts SET retry_evidence='not_submitted'",
            "UPDATE telnyx_policy_clock SET checked_at='2000-01-01T00:00:00+00:00'",
            "INSERT OR REPLACE INTO telnyx_policy_clock VALUES(1,'2000-01-01T00:00:00+00:00')",
            "DELETE FROM telnyx_policy_clock",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
    restarted = SqliteConversationStore(path)
    assert restarted.get_delivery(claim.delivery_id).first_submission_at == TIME
    assert not authorize(restarted, claim, now=TIME + timedelta(days=2))


@pytest.mark.parametrize("marked", [False, True])
def test_replace_cannot_erase_telnyx_attempt_evidence(ingress, marked):
    store, path, claim = prepare(ingress)
    if marked:
        assert authorize(store, claim)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        before = connection.execute("SELECT * FROM delivery_attempts").fetchall()
        with pytest.raises(sqlite3.IntegrityError, match="already exists"):
            connection.execute(
                "INSERT OR REPLACE INTO delivery_attempts "
                "(id,outbound_delivery_id,attempt_number,owner_token,outcome,started_at) "
                "SELECT id,outbound_delivery_id,attempt_number,owner_token,outcome,started_at "
                "FROM delivery_attempts"
            )
        assert connection.execute("SELECT * FROM delivery_attempts").fetchall() == before


def test_commit_failure_rolls_back_and_redacts_sql_error(ingress, monkeypatch, caplog):
    store, path, claim = prepare(ingress)
    original = store._connect

    @contextmanager
    def fail_commit(*args, **kwargs):
        with original(*args, **kwargs) as connection:
            yield connection
            raise sqlite3.OperationalError(PRIVATE_TEXT + PHONE + CUSTOMER)

    monkeypatch.setattr(store, "_connect", fail_commit)
    with pytest.raises(PersistenceUnavailable) as caught:
        authorize(store, claim)
    rendered = "".join(traceback.format_exception(caught.value)) + caplog.text
    for sentinel in (PRIVATE_TEXT, PHONE, CUSTOMER, claim.submission_key):
        assert sentinel not in rendered
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT submission_started_at,first_submission_at FROM outbound_deliveries"
        ).fetchone() == (None, None)
        assert connection.execute("SELECT * FROM telnyx_policy_clock").fetchall() == []
    monkeypatch.setattr(store, "_connect", original)
    assert authorize(store, claim)


def test_fake_runner_receives_durable_identity_outside_sqlite_transaction(ingress):
    _, store, path = ingress
    pending(store)

    class InspectingFake(DeterministicFakeOutboundSender):
        def send(self, message, *, timeout_seconds):
            with sqlite3.connect(path, timeout=0) as connection:
                connection.execute("BEGIN IMMEDIATE")
                marker, key = connection.execute(
                    "SELECT first_submission_at,submission_key FROM outbound_deliveries"
                ).fetchone()
                assert marker == TIME.isoformat()
                assert key == message.submission_key
            return super().send(message, timeout_seconds=timeout_seconds)

    fake = InspectingFake(outcomes=[ProviderAcceptance("synthetic-provider-id")])
    result = OutboundDeliveryRunner(store, fake, 1, provider="telnyx").run_once(now=TIME)
    assert result.state is DeliveryState.ACCEPTED
    assert len(fake.calls) == 1
    sent, timeout = fake.calls[0]
    assert sent == outbound(result)
    assert timeout == 1


@pytest.mark.parametrize("missing", ["consent", "window"])
def test_ineligible_runner_never_calls_sender_and_stale_claim_becomes_unknown(ingress, missing):
    _, store, path = ingress
    pending(store)
    with sqlite3.connect(path) as connection:
        table = "telnyx_consent" if missing == "consent" else "inbound_event_receipts"
        connection.execute(f"DELETE FROM {table}")
    fake = DeterministicFakeOutboundSender(outcomes=[])
    runner = OutboundDeliveryRunner(store, fake, 1, provider="telnyx")
    with pytest.raises(DeliveryOwnershipLost):
        runner.run_once(now=TIME)
    assert fake.calls == []
    assert runner.run_once(now=TIME + timedelta(seconds=31)) is None
    assert store.get_delivery(1).state is DeliveryState.UNKNOWN
    assert fake.calls == []


def test_generic_fake_retryable_response_after_marker_remains_unknown(ingress):
    _, store, _ = ingress
    pending(store)
    fake = DeterministicFakeOutboundSender(outcomes=[OutboundRetryableError("synthetic-response")])
    runner = OutboundDeliveryRunner(store, fake, 1, provider="telnyx")
    assert runner.run_once(now=TIME).state is DeliveryState.UNKNOWN
    assert runner.run_once(now=TIME + timedelta(days=2)) is None
    assert len(fake.calls) == 1
