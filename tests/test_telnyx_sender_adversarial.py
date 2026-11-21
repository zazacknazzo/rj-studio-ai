"""Adversarial offline seams. AUD01 known-gap tests reproduce risk, NOT mitigation."""

import sqlite3
import traceback
from contextlib import contextmanager
from datetime import timedelta

import pytest
from test_telnyx_authentication import PHONE, PRIVATE_TEXT
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_delivery_status import pending, status_wire
from test_telnyx_lifecycle import account
from test_telnyx_messages import CUSTOMER, TIME, receive, wire
from test_telnyx_messages import ingress as ingress
from test_telnyx_request import signer as signer
from test_telnyx_sender import MESSAGE_ID, acceptance, response
from test_telnyx_sender_integration import runner
from test_telnyx_submission import outbound, prepare
from test_telnyx_submission_migration import backup

from rj_studio_ai.delivery import DeliveryOwnershipLost
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.telnyx_sender import TelnyxWhatsAppSender


def authorize(store, claim, signer, *, now=TIME):
    request = signer.prepare(outbound(claim))
    return store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=request.message,
        http_request=request,
        now=now,
    )


def never_exchange(*_, **__):
    pytest.fail("No exchange may occur in this scenario")


@pytest.mark.parametrize("phase", ["authorization", "acceptance"])
def test_commit_failure_rolls_back_binding_or_acceptance_without_resend(
    ingress,
    signer,
    monkeypatch,
    caplog,
    phase,
):
    _, store, path = ingress
    pending(store)
    original = store._connect
    calls = []

    @contextmanager
    def fail_commit(*args, **kwargs):
        with original(*args, **kwargs) as db:
            yield db
            raise sqlite3.OperationalError(PRIVATE_TEXT + PHONE + CUSTOMER)

    if phase == "authorization":
        original_authorize = store.authorize_delivery_submission

        def fail_authorize(**kwargs):
            with monkeypatch.context() as patch:
                patch.setattr(store, "_connect", fail_commit)
                return original_authorize(**kwargs)

        monkeypatch.setattr(store, "authorize_delivery_submission", fail_authorize)

    def exchange(request, **_):
        calls.append(request)
        if phase == "acceptance":
            monkeypatch.setattr(store, "_connect", fail_commit)
        return response(acceptance(request))

    with pytest.raises(PersistenceUnavailable) as raised:
        runner(store, signer, exchange).run_once(now=TIME)
    assert "Synthetic reply" not in "".join(traceback.format_exception(raised.value)) + caplog.text
    assert PRIVATE_TEXT not in "".join(traceback.format_exception(raised.value)) + caplog.text
    monkeypatch.setattr(store, "_connect", original)
    with store._connect() as db:
        bound = db.execute("SELECT COUNT(*) FROM telnyx_http_requests").fetchone()[0]
        assert bound == (1 if phase == "acceptance" else 0)
        assert db.execute(
            "SELECT state,provider_message_id FROM outbound_deliveries"
        ).fetchone() == ("sending", None)
        assert db.execute("SELECT outcome FROM delivery_attempts").fetchone() == ("started",)
    restarted = SqliteConversationStore(path)
    assert (
        runner(restarted, signer, never_exchange).run_once(now=TIME + timedelta(seconds=31)) is None
    )
    assert len(calls) == (1 if phase == "acceptance" else 0)
    assert restarted.list_blocked_deliveries()[0].state is DeliveryState.UNKNOWN


@pytest.mark.parametrize("when", ["before_exchange", "after_possible_send"])
def test_crash_after_marker_never_replays(ingress, signer, when):
    store, path, claim = prepare(ingress)
    assert authorize(store, claim, signer)
    calls = []
    if when == "after_possible_send":

        def exchange(request, **_):
            calls.append(request)
            raise SystemExit("synthetic crash after possible send")

        with pytest.raises(SystemExit):
            TelnyxWhatsAppSender(signer, exchange).send_prepared(
                signer.prepare(outbound(claim)), timeout_seconds=9
            )
    restarted = SqliteConversationStore(path)
    assert runner(restarted, signer, never_exchange).run_once(now=TIME + timedelta(days=2)) is None
    result = restarted.get_delivery(claim.delivery_id)
    assert result.state is DeliveryState.UNKNOWN and result.submission_key == claim.submission_key
    assert len(calls) == (1 if when == "after_possible_send" else 0)


@pytest.mark.parametrize("transition", ["echo", "ACCOUNT_OFFBOARDED", "ACCOUNT_RECONNECTED"])
def test_pause_or_lifecycle_between_prepare_and_marker_prevents_transport(
    ingress,
    signer,
    private_key,
    monkeypatch,
    transition,
):
    _, store, _ = ingress
    pending(store)
    original = TelnyxWhatsAppSender.prepare

    def change(self, message):
        request = original(self, message)
        payload = wire("echo") if transition == "echo" else account(transition)
        receive(ingress, private_key, payload)
        return request

    monkeypatch.setattr(TelnyxWhatsAppSender, "prepare", change)
    result = runner(store, signer, never_exchange).run_once(now=TIME)
    assert result.state is DeliveryState.CANCELLED and result.first_submission_at is None
    with store._connect() as db:
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []


def test_pause_after_marker_preserves_possible_send(ingress, signer, private_key):
    _, store, _ = ingress
    pending(store)

    def exchange(request, **_):
        receive(ingress, private_key, wire("echo"))
        return response(acceptance(request))

    result = runner(store, signer, exchange).run_once(now=TIME)
    assert result.state is DeliveryState.ACCEPTED and result.first_submission_at == TIME
    assert store.claim_next_delivery(now=TIME) is None


@pytest.mark.parametrize("gate", ["handoff", "conflict"])
def test_handoff_and_delivery_conflict_between_prepare_and_marker(
    ingress, signer, monkeypatch, gate
):
    _, store, path = ingress
    pending(store)
    original = TelnyxWhatsAppSender.prepare

    def change(self, message):
        request = original(self, message)
        with store._connect() as db:
            if gate == "conflict":
                db.execute("UPDATE outbound_deliveries SET status_conflict=1")
            else:
                conversation_id = db.execute("SELECT id FROM conversations").fetchone()[0]
                db.execute(
                    "INSERT INTO conversation_handoffs(conversation_id,active,reason_code,"
                    "owner_token,activated_at) VALUES(?,1,'explicit_human_request',"
                    "'synthetic-owner',?)",
                    (conversation_id, TIME.isoformat()),
                )
        return request

    monkeypatch.setattr(TelnyxWhatsAppSender, "prepare", change)
    with pytest.raises(DeliveryOwnershipLost):
        runner(store, signer, never_exchange).run_once(now=TIME)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []


def test_conflicting_early_status_rolls_back_acceptance_then_unknown(ingress, signer, private_key):
    _, store, path = ingress
    pending(store)

    def exchange(request, **_):
        wrong = status_wire("delivered", message_id=MESSAGE_ID)
        wrong["data"]["payload"]["to"][0]["phone_number"] = "+5511888888888"
        receive(ingress, private_key, wrong)
        return response(acceptance(request))

    with pytest.raises(ValueError, match="^Delivery correlation scope mismatch$"):
        runner(store, signer, exchange).run_once(now=TIME)
    restarted = SqliteConversationStore(path)
    assert (
        runner(restarted, signer, never_exchange).run_once(now=TIME + timedelta(seconds=31)) is None
    )
    with restarted._connect() as db:
        assert db.execute(
            "SELECT state,provider_message_id FROM outbound_deliveries"
        ).fetchone() == ("unknown", None)
        assert db.execute("SELECT COUNT(*) FROM delivery_status_events").fetchone() == (1,)


def test_bsuid_never_reaches_transport(ingress, signer):
    _, store, _ = ingress
    pending(store, customer="bsuid:US.13491208655302741918")
    result = runner(store, signer, never_exchange).run_once(now=TIME)
    assert result.state is DeliveryState.RETRYABLE
    assert result.first_submission_at is None
    assert store.get_delivery_attempts(result.delivery_id)[0].retry_evidence == "not_submitted"


def test_purge_retains_request_identity_and_reused_numeric_id_has_new_key(ingress, signer):
    _, store, path = ingress
    pending(store)
    first = runner(store, signer, lambda r, **_: response(acceptance(r))).run_once(now=TIME)
    assert store.purge_messages_older_than(TIME + timedelta(days=1)).messages_deleted == 2
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM telnyx_http_requests").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM delivery_attempts").fetchone() == (0,)
    pending(store, message_id="new-after-purge")
    second = store.claim_next_delivery(now=TIME + timedelta(seconds=1))
    assert second.delivery_id == first.delivery_id and second.submission_key != first.submission_key
    assert authorize(store, second, signer, now=TIME + timedelta(seconds=1))


@pytest.mark.parametrize("point", ["before_claim", "before_marker", "before_disconnect"])
def test_aud01_known_gap_old_snapshot_can_erase_fences(
    ingress, signer, private_key, tmp_path, point
):
    """PASS demonstrates OPEN AUD01; operational quarantine is NOT implemented."""
    _, store, path = ingress
    pending(store)
    if point != "before_claim":
        claim = store.claim_next_delivery(now=TIME)
    old = tmp_path / "stale-synthetic.db"
    backup(path, old)
    if point == "before_claim":
        claim = store.claim_next_delivery(now=TIME)
    if point == "before_disconnect":
        receive(ingress, private_key, account())
        assert not authorize(store, claim, signer)
    else:
        assert authorize(store, claim, signer)
        assert store.finalize_delivery(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            outcome=DeliveryState.ACCEPTED,
            provider_message_id=MESSAGE_ID,
            now=TIME,
        )
    restored = SqliteConversationStore(old)
    restored.initialize()
    assert restored.migrations_are_current()  # integrity/current schema != freshness
    if point == "before_claim":
        old_key = claim.submission_key
        claim = restored.claim_next_delivery(now=TIME + timedelta(seconds=1))
        assert claim.submission_key == old_key
    assert authorize(restored, claim, signer, now=TIME + timedelta(seconds=1))
    # Deliberately NEVER pass this restored authorization to a transport.


def test_restore_after_acceptance_retains_no_resend_even_after_key_expiry(
    ingress, signer, tmp_path
):
    _, store, path = ingress
    pending(store)
    accepted = runner(store, signer, lambda r, **_: response(acceptance(r))).run_once(now=TIME)
    old = tmp_path / "accepted-synthetic.db"
    backup(path, old)
    restored = SqliteConversationStore(old)
    restored.initialize()
    assert runner(restored, signer, never_exchange).run_once(now=TIME + timedelta(days=2)) is None
    assert restored.get_delivery(accepted.delivery_id).state is DeliveryState.ACCEPTED


def test_aud01_known_gap_external_expiry_does_not_make_stale_copy_safe(ingress, signer, tmp_path):
    """Fresh policy evidence cannot recover lost submission evidence: AUD01 OPEN."""
    _, store, path = ingress
    pending(store)
    old = tmp_path / "before-claim.db"
    backup(path, old)
    accepted = runner(store, signer, lambda r, **_: response(acceptance(r))).run_once(now=TIME)
    restored = SqliteConversationStore(old)
    later = TIME + timedelta(days=2)
    # Synthetic fresh inbound/consent on restored timeline; not operational verification.
    with restored._connect() as db:
        db.execute(
            "UPDATE telnyx_consent SET expires_at=?", ((later + timedelta(days=1)).isoformat(),)
        )
        db.execute(
            "UPDATE inbound_event_receipts SET message_occurred_at=?,occurred_at=?,received_at=?",
            (later.isoformat(),) * 3,
        )
    claim = restored.claim_next_delivery(now=later)
    assert claim.submission_key == accepted.submission_key
    assert authorize(restored, claim, signer, now=later)  # unsafe local behavior, no exchange
