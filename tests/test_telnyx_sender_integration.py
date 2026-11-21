"""Actual runner + SQLite writer/markers/status ledger, intercepted exchange only."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_delivery_status import pending, status_wire
from test_telnyx_lifecycle import account
from test_telnyx_messages import TIME, receive
from test_telnyx_messages import ingress as ingress
from test_telnyx_request import signer as signer
from test_telnyx_sender import MESSAGE_ID, acceptance, response
from test_telnyx_submission import outbound, prepare

from rj_studio_ai.delivery import DeliveryOwnershipLost, OutboundDeliveryRunner
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.telnyx_sender import TelnyxWhatsAppSender
from rj_studio_ai.telnyx_request import InvalidTelnyxRequest


def runner(store, signer, exchange):
    return OutboundDeliveryRunner(
        store, TelnyxWhatsAppSender(signer, exchange), 9, provider="telnyx"
    )


def test_runner_commits_exact_binding_and_markers_before_unlocked_exchange(ingress, signer):
    _, store, path = ingress
    pending(store)
    seen = []

    def exchange(request, **policy):
        with store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            identity = db.execute("SELECT * FROM telnyx_http_requests").fetchone()
            assert identity == (
                request.message.submission_key,
                "t11-v1",
                signer.integrity_key_id,
                request.request_mac,
            )
            assert (
                db.execute(
                    "SELECT first_submission_at,submission_started_at FROM outbound_deliveries"
                ).fetchone()
                == (TIME.isoformat(),) * 2
            )
            assert db.execute("SELECT submission_started_at FROM delivery_attempts").fetchone() == (
                TIME.isoformat(),
            )
        seen.append((request, policy))
        return response(acceptance(request))

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.ACCEPTED
    assert result.provider_message_id == MESSAGE_ID
    assert len(seen) == 1
    restarted = SqliteConversationStore(path)
    assert runner(restarted, signer, exchange).run_once(now=TIME + timedelta(days=2)) is None
    assert len(seen) == 1


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (409, "10036", "telnyx_in_progress"),
        (422, "10027", "telnyx_key_conflict"),
        (429, "other", "telnyx_http_unknown"),
        (500, "other", "telnyx_http_unknown"),
        (503, "other", "telnyx_http_unknown"),
        (409, "other", "telnyx_http_unknown"),
        (422, "other", "telnyx_http_unknown"),
    ],
)
def test_unknown_persists_without_new_key_or_resend(ingress, signer, status, code, expected):
    _, store, path = ingress
    pending(store)
    calls = []

    def exchange(request, **_):
        calls.append(request)
        return response({"errors": [{"code": code}]}, status)

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.UNKNOWN
    assert result.safe_error_code == expected
    restarted = SqliteConversationStore(path)
    for now in (TIME + timedelta(seconds=1), TIME + timedelta(days=2)):
        assert runner(restarted, signer, exchange).run_once(now=now) is None
    assert len(calls) == 1
    assert calls[0].message.submission_key == result.submission_key


@pytest.mark.parametrize("timing", ["before", "after"])
def test_scoped_callback_before_or_after_response(ingress, signer, private_key, timing):
    _, store, _ = ingress
    pending(store)

    def callback():
        receive(ingress, private_key, status_wire("delivered", message_id=MESSAGE_ID))

    def exchange(request, **_):
        if timing == "before":
            callback()
            with store._connect() as db:
                assert db.execute("SELECT state FROM outbound_deliveries").fetchone() == (
                    "sending",
                )
        return response(acceptance(request, status="read"))

    result = runner(store, signer, exchange).run_once(now=TIME)
    if timing == "after":
        assert result.state is DeliveryState.ACCEPTED  # response read does not advance ledger
        callback()
    assert store.get_delivery(result.delivery_id).state is DeliveryState.DELIVERED


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE telnyx_consent SET revoked_at='invalid'",
        "UPDATE inbound_event_receipts SET message_occurred_at='2000-01-01T00:00:00+00:00'",
    ],
)
def test_prepare_does_not_cache_authorization_gates(ingress, signer, monkeypatch, mutation):
    _, store, path = ingress
    pending(store)
    original = TelnyxWhatsAppSender.prepare

    def prepare_then_block(self, message):
        result = original(self, message)
        with sqlite3.connect(path) as db:
            db.execute(mutation)
        return result

    monkeypatch.setattr(TelnyxWhatsAppSender, "prepare", prepare_then_block)

    def unexpected(*_, **__):
        pytest.fail("exchange invoked")

    with pytest.raises(DeliveryOwnershipLost):
        runner(store, signer, unexpected).run_once(now=TIME)
    with store._connect() as db:
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []
        assert db.execute("SELECT first_submission_at FROM outbound_deliveries").fetchone() == (
            None,
        )


def test_local_preparation_failure_has_attempt_scoped_non_submission(ingress, signer, monkeypatch):
    _, store, _ = ingress
    pending(store)
    original = TelnyxWhatsAppSender.prepare

    def fail(self, message):
        raise InvalidTelnyxRequest("private failure")

    monkeypatch.setattr(TelnyxWhatsAppSender, "prepare", fail)

    def unexpected(*_, **__):
        pytest.fail("exchange invoked")

    result = runner(store, signer, unexpected).run_once(now=TIME)
    assert result.state is DeliveryState.RETRYABLE
    attempt = store.get_delivery_attempts(result.delivery_id)[0]
    assert attempt.retry_evidence == "not_submitted" and attempt.submission_started_at is None
    monkeypatch.setattr(TelnyxWhatsAppSender, "prepare", original)
    result2 = runner(store, signer, lambda request, **_: response(acceptance(request))).run_once(
        now=TIME + timedelta(seconds=1)
    )
    assert result2.state is DeliveryState.ACCEPTED
    assert result2.submission_key == result.submission_key


@pytest.mark.parametrize(
    "field,value",
    [("organization_id", "other"), ("profile_id", "00000000-0000-4000-8000-000000000000")],
)
def test_wrong_authorized_scope_never_exchanges(ingress, signer, field, value):
    _, store, _ = ingress
    pending(store)

    def unexpected(*_, **__):
        pytest.fail("exchange invoked")

    with pytest.raises(DeliveryOwnershipLost):
        runner(store, replace(signer, **{field: value}), unexpected).run_once(now=TIME)


def test_workers_claim_and_authorize_exactly_once(ingress, signer):
    _, store, path = ingress
    pending(store)
    barrier = Barrier(2)
    calls = []

    def exchange(request, **_):
        calls.append(request)
        return response(acceptance(request))

    def run():
        other = SqliteConversationStore(path)
        barrier.wait()
        return runner(other, signer, exchange).run_once(now=TIME)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(r is not None for r in results) == len(calls) == 1
    assert len(store.get_delivery_attempts(next(r for r in results if r).delivery_id)) == 1


def test_owner_and_expired_lease_cannot_bind_or_submit(ingress, signer):
    store, _, claim = prepare(ingress)
    request = signer.prepare(outbound(claim))
    for owner, now in [("other", TIME), (claim.owner_token, TIME + timedelta(seconds=31))]:
        assert not store.authorize_delivery_submission(
            delivery_id=claim.delivery_id,
            owner_token=owner,
            now=now,
            message=request.message,
            http_request=request,
        )
    with store._connect() as db:
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []


def test_disconnect_after_marker_exposes_residual_window(ingress, signer, private_key):
    _, store, _ = ingress
    pending(store)
    calls = []

    def exchange(request, **_):
        receive(ingress, private_key, account())
        calls.append(request)
        return response(acceptance(request))

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.ACCEPTED
    assert len(calls) == 1
    assert store.claim_next_delivery(now=TIME) is None
