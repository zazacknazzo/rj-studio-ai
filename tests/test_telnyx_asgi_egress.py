"""Closed offline composition + exact-request negatives; no operational release."""

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest
from starlette.testclient import TestClient
from test_telnyx_asgi import post
from test_telnyx_authentication import NOW
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_delivery_status import pending, status_wire
from test_telnyx_lifecycle import account
from test_telnyx_messages import TIME, receive, wire
from test_telnyx_messages import ingress as ingress
from test_telnyx_request import signer as signer
from test_telnyx_sender import MESSAGE_ID, acceptance, response
from test_telnyx_sender_integration import runner
from test_telnyx_submission import outbound, prepare
from test_telnyx_submission_migration import backup

from rj_studio_ai.delivery import DeliveryOwnershipLost, OutboundDeliveryRunner
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.telnyx_asgi import OfflineTelnyxASGI, create_telnyx_offline_app


def test_direct_composition_cannot_accept_unquarantined_store(settings, tmp_path):
    store = SqliteConversationStore(tmp_path / "unfenced.db")
    with pytest.raises(ValueError, match="requires quarantine"):
        OfflineTelnyxASGI(settings, store, wall_clock=lambda: NOW, clock=lambda: 0)


def test_restore_before_claim_denies_an_otherwise_eligible_new_owner(
    ingress, signer, settings, tmp_path
):
    _, store, path = ingress
    pending(store)
    snapshot = tmp_path / "pending.db"
    backup(path, snapshot)
    accepted = runner(store, signer, lambda r, **_: response(acceptance(r))).run_once(now=TIME)
    assert accepted.state is DeliveryState.ACCEPTED
    app = create_telnyx_offline_app(settings, snapshot, wall_clock=lambda: NOW)
    restored_claim = app.store.claim_next_delivery(provider="telnyx", now=TIME)
    request = signer.prepare(outbound(restored_claim))
    legacy = SqliteConversationStore(snapshot)
    assert legacy.assess_telnyx_submission(
        delivery_id=restored_claim.delivery_id,
        owner_token=restored_claim.owner_token,
        message=request.message,
        now=TIME,
    ).eligible  # Demonstrates why SQLite alone does NOT solve AUD01.
    assert not app.store.authorize_delivery_submission(
        delivery_id=restored_claim.delivery_id,
        owner_token=restored_claim.owner_token,
        message=request.message,
        http_request=request,
        now=TIME,
    )
    assert restored_claim.submission_key == accepted.submission_key


@pytest.mark.parametrize(
    "point",
    [
        "before_claim",
        "before_marker",
        "before_disconnect",
        "old_after_acceptance",
        "after_acceptance",
        "external_expired",
    ],
)
def test_restore_and_restart_cannot_leave_offline_quarantine(
    ingress, signer, private_key, settings, tmp_path, point
):
    _, store, path = ingress
    pending(store)
    if point != "before_claim":
        claim = store.claim_next_delivery(now=TIME)
    snapshot = tmp_path / "restore.db"
    if point != "after_acceptance":
        backup(path, snapshot)
    if point == "before_disconnect":
        receive(ingress, private_key, account())
    else:
        if point == "before_claim":
            claim = store.claim_next_delivery(now=TIME)
        request = signer.prepare(outbound(claim))
        assert store.authorize_delivery_submission(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            message=request.message,
            http_request=request,
            now=TIME,
        )
        assert store.finalize_delivery(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            outcome=DeliveryState.ACCEPTED,
            provider_message_id=MESSAGE_ID,
            now=TIME,
        )
    if point == "after_acceptance":
        backup(path, snapshot)
    # Snapshot freshness/markers/active status are NOT trusted by the factory.
    for _ in range(2):
        app = create_telnyx_offline_app(settings, snapshot, wall_clock=lambda: NOW)
        assert app.readiness()["quarantined"] is True
        assert app.readiness()["egress"] is False
        assert not hasattr(app, "sender") and not hasattr(app, "executor")
        assert not hasattr(app, "release")
        now = TIME + timedelta(days=2) if point == "external_expired" else TIME
        assert not app.store.authorize_delivery_submission(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            message=outbound(claim),
            http_request=signer.prepare(outbound(claim)),
            now=now,
        )
        with TestClient(app) as client:
            assert client.post("/release-quarantine").status_code == 404
        with sqlite3.connect(snapshot) as db:
            assert db.execute("SELECT submission_key FROM outbound_deliveries").fetchone() == (
                claim.submission_key,
            )


@pytest.mark.parametrize("kind", ["missing", "bad_mac", "different_body", "wrong_scope"])
def test_strict_writer_refuses_missing_or_tampered_http_binding(ingress, signer, kind):
    store, path, claim = prepare(ingress)
    strict = SqliteConversationStore(path, telnyx_request_signer=signer)
    request = signer.prepare(outbound(claim))
    if kind == "missing":
        request = None
    elif kind == "bad_mac":
        request = replace(request, request_mac="0" * 64)
    elif kind == "different_body":
        request = replace(request, content=request.content + b" ")
    else:
        request = replace(request, organization_id="different-synthetic-org")
    assert not strict.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=outbound(claim),
        http_request=request,
        now=TIME,
    )
    assert store.get_delivery(claim.delivery_id).first_submission_at is None
    with store._connect() as db:
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []


def test_generic_sender_cannot_bypass_prepared_request_in_strict_composition(ingress, signer):
    _, store, path = ingress
    pending(store)
    strict = SqliteConversationStore(path, telnyx_request_signer=signer)
    sender = DeterministicFakeOutboundSender(outcomes=[])
    with pytest.raises(DeliveryOwnershipLost):
        OutboundDeliveryRunner(strict, sender, 1, provider="telnyx").run_once(now=TIME)
    assert sender.calls == []


def test_strict_intercepted_runner_retains_binding_and_all_policy_gates(ingress, signer):
    _, store, path = ingress
    pending(store)
    strict = SqliteConversationStore(path, telnyx_request_signer=signer)
    calls = []

    def exchange(request, **kwargs):
        with strict._connect() as db:
            assert db.execute("SELECT request_mac FROM telnyx_http_requests").fetchone() == (
                request.request_mac,
            )
        calls.append(request)
        return response(acceptance(request))

    result = runner(strict, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.ACCEPTED and len(calls) == 1


@pytest.mark.parametrize("gate", ["consent", "lifecycle", "pause", "owner", "lease", "window"])
def test_exact_binding_does_not_override_policy(ingress, signer, private_key, gate):
    _, store, path = ingress
    _, _, claim = prepare(ingress)
    strict = SqliteConversationStore(path, telnyx_request_signer=signer)
    request = signer.prepare(outbound(claim))
    if gate == "consent":
        with store._connect() as db:
            db.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))
    elif gate == "lifecycle":
        receive(ingress, private_key, account())
    elif gate == "pause":
        receive(ingress, private_key, wire("echo"))
    assert not strict.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token="wrong" if gate == "owner" else claim.owner_token,
        message=request.message,
        http_request=request,
        now=TIME
        + (
            timedelta(days=1)
            if gate == "window"
            else timedelta(seconds=31)
            if gate == "lease"
            else timedelta()
        ),
    )
    assert store.get_delivery(claim.delivery_id).first_submission_at is None


def test_callbacks_over_asgi_preserve_early_late_and_contradictory_evidence(
    ingress, signer, private_key, settings
):
    _, store, path = ingress
    pending(store)
    app = create_telnyx_offline_app(settings, path, wall_clock=lambda: NOW)
    with TestClient(app) as client:
        assert (
            post(client, private_key, status_wire("delivered", message_id=MESSAGE_ID)).status_code
            == 204
        )
        # Test-only intercepted runner, deliberately outside the closed ASGI composition.
        strict = SqliteConversationStore(path, telnyx_request_signer=signer)
        result = runner(
            strict, signer, lambda request, **_: response(acceptance(request))
        ).run_once(now=TIME)
        assert result.state is DeliveryState.DELIVERED
        assert (
            post(client, private_key, status_wire("read", message_id=MESSAGE_ID)).status_code == 204
        )
        assert (
            post(client, private_key, status_wire("failed", message_id=MESSAGE_ID)).status_code
            == 204
        )
    result = store.get_delivery(result.delivery_id)
    assert result.state is DeliveryState.READ
    with store._connect() as db:
        assert db.execute("SELECT status_conflict FROM outbound_deliveries").fetchone() == (1,)
    assert app.readiness()["operational_channel"] is False
