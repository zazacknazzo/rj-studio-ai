"""Restore/antirollback contract adversaries; real SQLite, synthetic external services."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from offline_recovery_fixture import RESOURCE, SQLiteAuthority, SQLiteWitness
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_lifecycle import account
from test_telnyx_messages import TIME, receive, wire
from test_telnyx_messages import ingress as ingress
from test_telnyx_submission import authorize, prepare

from rj_studio_ai.offline_recovery import (
    AuthorityReply,
    InventoryItem,
    OfflineRecoverySession,
    RecoveryClosed,
    snapshot_inventory,
)
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore


@pytest.fixture
def lab(ingress, tmp_path):
    _, store, path = ingress
    store, path, claim = prepare(ingress)
    authority = SQLiteAuthority(tmp_path / "independent-authority.db")
    genesis = authority.read(RESOURCE, "genesis", authority.tokens["application"]).state
    witness = SQLiteWitness(tmp_path / "independent-witness.db", genesis)
    authority.witness = witness
    quarantined = SqliteConversationStore(path, telnyx_egress_quarantined=True)

    def session():
        return OfflineRecoverySession(
            quarantined,
            authority,
            witness,
            resource=RESOURCE,
            application_credential=authority.tokens["application"],
        )

    return session, authority, witness, store, claim, path


def reconcile_all(session, authority, outcome="accepted"):
    for item in (
        authority.state_inventory()
        if hasattr(authority, "state_inventory")
        else (
            authority.read(RESOURCE, "inventory", authority.tokens["application"]).state.inventory
        )
    ):
        if item.outcome == "unknown":
            proof = authority.approve_reconciliation(
                authority.tokens["verifier"],
                intent_id=item.intent_id,
                outcome=outcome,
            )
            session.reconcile(
                authority.tokens["recoverer"],
                intent_id=item.intent_id,
                outcome=outcome,
                evidence_ref=proof,
            )


def release_lab(lab):
    make, authority, _, _, _, _ = lab
    session = make()
    session.begin(authority.tokens["recoverer"])
    reconcile_all(session, authority)
    authority.seed_current_proofs(authority.tokens["verifier"])
    session.release(authority.tokens["approver"])
    assert session.readiness()["simulation_ready"]
    return session


def backup(source, target):
    with sqlite3.connect(source) as original, sqlite3.connect(target) as copy:
        original.backup(copy)


def test_release_is_only_a_simulation_and_never_unquarantines_store(lab):
    session = release_lab(lab)
    _, authority, _, store, claim, path = lab
    result = session.readiness()
    assert not result["operational_egress"]
    assert not session._store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        now=TIME,
    )
    assert store.get_delivery(claim.delivery_id).first_submission_at is None
    assert result["blocked_intents"] == (
        authority.read(
            RESOURCE,
            "inspection",
            authority.tokens["application"],
        )
        .state.inventory[0]
        .intent_id,
    )
    assert path.exists()


def test_every_boot_and_repeated_restore_revokes_previous_session(lab):
    old = release_lab(lab)
    make, authority, _, _, _, _ = lab
    previous_epoch = old.readiness()["epoch"]
    for _ in range(3):
        new = make()
        assert not new.readiness()["simulation_ready"]
        new.begin(authority.tokens["recoverer"])
        assert not old.readiness()["simulation_ready"]
        assert not new.readiness()["simulation_ready"]
        assert new.readiness()["epoch"] > previous_epoch
        previous_epoch = new.readiness()["epoch"]


@pytest.mark.parametrize("transition", ["accepted", "disconnect", "pause", "revoke_consent"])
def test_old_snapshot_loses_markers_but_not_independent_inventory(
    lab, tmp_path, transition, ingress, private_key
):
    make, authority, _, store, claim, path = lab
    old_snapshot = tmp_path / "before.db"
    backup(path, old_snapshot)
    session = make()
    session.begin(authority.tokens["recoverer"])
    if transition == "accepted":
        assert authorize(store, claim)
        assert store.finalize_delivery(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            outcome=DeliveryState.ACCEPTED,
            provider_message_id="synthetic-accepted",
            now=TIME,
        )
    elif transition == "disconnect":
        assert receive(ingress, private_key, account("PARTNER_REMOVED")).status_code == 204
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT state FROM channel_lifecycle").fetchone() == ("blocked",)
    elif transition == "pause":
        assert receive(ingress, private_key, wire("echo")).status_code == 204
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT paused FROM conversation_automation_controls").fetchone() == (
                1,
            )
    else:
        with sqlite3.connect(path) as db:
            db.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))
    backup(old_snapshot, path)
    restored = make()
    restored.begin(authority.tokens["recoverer"])
    state = authority.read(RESOURCE, "inspect", authority.tokens["application"]).state
    assert len(state.inventory) == 1 and state.inventory[0].submission_key == claim.submission_key
    assert state.inventory[0].outcome == "unknown"
    assert not restored.readiness()["simulation_ready"]
    assert store.get_delivery(claim.delivery_id).first_submission_at is None
    assert not restored._store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        now=TIME,
    )


@pytest.mark.parametrize("role", ["application", "recoverer", "verifier", "security"])
def test_application_and_recoverer_cannot_self_approve(lab, role):
    make, authority, _, _, _, _ = lab
    session = make()
    session.begin(authority.tokens["recoverer"])
    reconcile_all(session, authority)
    authority.seed_current_proofs(authority.tokens["verifier"])
    with pytest.raises(RecoveryClosed):
        session.release(authority.tokens[role])
    assert not session.readiness()["simulation_ready"]


@pytest.mark.parametrize(
    "missing",
    ["binding_ref", "sync_ref", "consent_ref", "window_ref"],
)
def test_current_scoped_evidence_is_required(lab, missing):
    make, authority, _, _, _, _ = lab
    session = make()
    session.begin(authority.tokens["recoverer"])
    reconcile_all(session, authority)
    authority.seed_current_proofs(authority.tokens["verifier"], missing=missing)
    with pytest.raises(RecoveryClosed):
        session.release(authority.tokens["approver"])


def test_unknown_cannot_be_reconciled_without_proof_or_as_retryable(lab):
    make, authority, _, _, claim, _ = lab
    session = make()
    state = session.begin(authority.tokens["recoverer"])
    item = state.inventory[0]
    with pytest.raises(RecoveryClosed):
        session.reconcile(
            authority.tokens["recoverer"],
            intent_id=item.intent_id,
            outcome="retryable",
            evidence_ref="not-a-proof",
        )
    assert item.submission_key == claim.submission_key and item.outcome == "unknown"
    with pytest.raises(RecoveryClosed):
        session.reconcile(
            authority.tokens["recoverer"],
            intent_id=item.intent_id,
            outcome="accepted",
            evidence_ref="forged-proof",
        )
    assert not session.readiness()["simulation_ready"]


@pytest.mark.parametrize("outcome", ["accepted", "not_submitted"])
def test_reconciled_old_work_never_gains_new_key_or_replay(lab, outcome):
    make, authority, _, _, claim, _ = lab
    session = make()
    state = session.begin(authority.tokens["recoverer"])
    reconcile_all(session, authority, outcome)
    authority.seed_current_proofs(authority.tokens["verifier"])
    session.release(authority.tokens["approver"])
    assert session.readiness()["simulation_ready"]
    with pytest.raises(RecoveryClosed):
        session.record_possible_submission(
            InventoryItem(
                state.inventory[0].intent_id,
                str(uuid4()),
                "different-request",
            )
        )
    assert (
        authority.read(RESOURCE, "check", authority.tokens["application"])
        .state.inventory[0]
        .submission_key
        == claim.submission_key
    )


def test_write_ahead_inventory_survives_crash_without_local_marker(lab):
    session = release_lab(lab)
    make, authority, _, store, claim, _ = lab
    item = InventoryItem("synthetic-new-intent", str(uuid4()), "synthetic-request-digest")
    session.record_possible_submission(item)
    # Crash occurs before any local marker/transport. Conservative unknown is retained.
    restarted = make()
    state = restarted.begin(authority.tokens["recoverer"])
    assert item.submission_key in {i.submission_key for i in state.inventory}
    assert not restarted.readiness()["simulation_ready"]
    assert store.get_delivery(claim.delivery_id).first_submission_at is None


@pytest.mark.parametrize("same_epoch", [False, True])
def test_rollback_authority_cannot_revive_release(lab, tmp_path, same_epoch):
    session = release_lab(lab)
    make, authority, _, _, _, _ = lab
    saved = tmp_path / "old-authority.db"
    backup(authority.path, saved)
    if same_epoch:
        session.revoke(authority.tokens["security"])
    else:
        make().begin(authority.tokens["recoverer"])
    backup(saved, authority.path)
    assert not session.readiness()["simulation_ready"]
    with pytest.raises(RecoveryClosed):
        make().begin(authority.tokens["recoverer"])


def test_rollback_before_application_observes_revocation_is_detected(lab, tmp_path):
    session = release_lab(lab)
    _, authority, _, _, _, _ = lab
    old = tmp_path / "authority-before-access-revoke.db"
    backup(authority.path, old)
    authority.revoke_access(authority.tokens["security"], authority.tokens["approver"])
    backup(old, authority.path)
    assert not session.readiness()["simulation_ready"]


@pytest.mark.parametrize("failure", ["authority", "witness", "clock", "reply"])
def test_external_failure_latches_closed_without_cached_release(lab, failure):
    session = release_lab(lab)
    _, authority, witness, _, _, _ = lab
    if failure == "authority":
        authority.available = False
    elif failure == "witness":
        witness.available = False
    elif failure == "clock":
        authority.now -= 1
    else:
        state = authority.read(RESOURCE, "once", authority.tokens["application"]).state
        authority.stale_reply = AuthorityReply("old-challenge", state, authority.now)
    assert not session.readiness()["simulation_ready"]
    authority.available = witness.available = True
    authority.stale_reply = None
    authority.now += 2
    assert not session.readiness()["simulation_ready"]


def test_evidence_expires_and_access_revocation_invalidates_release(lab):
    session = release_lab(lab)
    _, authority, _, _, _, _ = lab
    authority.now += 60
    assert not session.readiness()["simulation_ready"]


def test_partial_commit_after_witness_is_quarantined(lab):
    session = release_lab(lab)
    make, authority, _, _, _, _ = lab
    authority.fail_commit = True
    with pytest.raises(RecoveryClosed):
        session.revoke(authority.tokens["security"])
    assert not session.readiness()["simulation_ready"]
    with pytest.raises(RecoveryClosed):
        make().begin(authority.tokens["recoverer"])


def test_same_revision_equivocation_is_rejected(lab):
    session = release_lab(lab)
    _, authority, _, _, _, _ = lab
    with sqlite3.connect(authority.path) as db:
        row = db.execute("SELECT body FROM state").fetchone()[0]
        from offline_recovery_fixture import decode

        current = decode(row)
        import json
        from dataclasses import asdict

        db.execute(
            "UPDATE state SET body=?",
            (json.dumps(asdict(replace(current, binding_ref="contradictory-same-revision"))),),
        )
    assert not session.readiness()["simulation_ready"]


def test_concurrent_recoveries_have_one_current_session(lab):
    make, authority, _, _, _, _ = lab
    sessions = [make(), make()]

    def begin(session):
        try:
            session.begin(authority.tokens["recoverer"])
            return True
        except RecoveryClosed:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(begin, sessions))
    assert any(outcomes)
    states = [s.readiness() for s in sessions]
    assert sum(s["epoch"] is not None for s in states) <= 1
    assert all(not s["simulation_ready"] for s in states)


def test_snapshot_modification_invalidates_release_and_audit_has_no_credentials(lab):
    session = release_lab(lab)
    _, authority, _, _, _, path = lab
    with sqlite3.connect(path) as db:
        db.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))
    assert not session.readiness()["simulation_ready"]
    with sqlite3.connect(authority.path) as db:
        audit = repr(db.execute("SELECT * FROM audit").fetchall())
        assert all(token not in audit for token in authority.tokens.values())
        assert "synthetic-service-consent" not in audit
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM audit")


def test_snapshot_inventory_is_deterministic_and_constructor_requires_quarantine(lab):
    _, authority, witness, store, _, path = lab
    assert snapshot_inventory(path) == snapshot_inventory(path)
    with pytest.raises(ValueError):
        OfflineRecoverySession(
            store,
            authority,
            witness,
            resource=RESOURCE,
            application_credential=authority.tokens["application"],
        )


@pytest.mark.parametrize("point", ["before_generation", "before_claim", "after_acceptance"])
def test_early_and_accepted_snapshots_preserve_external_only_inventory(ingress, tmp_path, point):
    from test_telnyx_delivery_status import pending

    _, store, path = ingress
    snapshot = tmp_path / "snapshot.db"
    if point == "before_generation":
        backup(path, snapshot)
    pending(store)
    if point == "before_claim":
        backup(path, snapshot)
    claim = store.claim_next_delivery(now=TIME)
    authority = SQLiteAuthority(tmp_path / "authority.db")
    witness = SQLiteWitness(tmp_path / "witness.db", authority.state())
    authority.witness = witness
    quarantined = SqliteConversationStore(path, telnyx_egress_quarantined=True)

    def make():
        return OfflineRecoverySession(
            quarantined,
            authority,
            witness,
            resource=RESOURCE,
            application_credential=authority.tokens["application"],
        )

    current = make()
    current.begin(authority.tokens["recoverer"])
    assert authorize(store, claim)
    assert store.finalize_delivery(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        outcome=DeliveryState.ACCEPTED,
        provider_message_id="synthetic-accepted",
        now=TIME,
    )
    # Reconciliation is against the independent synthetic oracle, not restored DB.
    proof = authority.approve_reconciliation(
        authority.tokens["verifier"],
        intent_id=authority.state().inventory[0].intent_id,
        outcome="accepted",
    )
    state = authority.state()
    authority.reconcile(
        RESOURCE,
        "reconcile-live",
        authority.tokens["recoverer"],
        expected_revision=state.revision,
        session_id=state.session_id,
        intent_id=state.inventory[0].intent_id,
        outcome="accepted",
        evidence_ref=proof,
    )
    if point == "after_acceptance":
        backup(path, snapshot)
    backup(snapshot, path)
    restored = make()
    restored.begin(authority.tokens["recoverer"])
    inventory = authority.state().inventory
    assert len(inventory) == 1 and inventory[0].submission_key == claim.submission_key
    assert inventory[0].outcome == "accepted"
    assert not restored.readiness()["simulation_ready"]
    assert not restored.readiness()["operational_egress"]
    if point == "before_generation":
        assert snapshot_inventory(path)[1] == ()
    with pytest.raises(RecoveryClosed):
        restored.record_possible_submission(replace(inventory[0], submission_key=str(uuid4())))


@pytest.mark.parametrize("after_boot", [False, True])
def test_authority_rollback_is_detected_even_without_read_after_revocation(
    lab, tmp_path, after_boot
):
    make, authority, _, _, _, _ = lab
    old_authority = tmp_path / "old-authority.db"
    if not after_boot:
        backup(authority.path, old_authority)
    session = release_lab(lab)
    if after_boot:
        backup(authority.path, old_authority)
        state = authority.state()
        authority.revoke(
            RESOURCE,
            "security-independent",
            authority.tokens["security"],
            expected_revision=state.revision,
        )
    backup(old_authority, authority.path)
    assert not session.readiness()["simulation_ready"]
    with pytest.raises(RecoveryClosed):
        make().begin(authority.tokens["recoverer"])


@pytest.mark.parametrize("missing", ["binding_ref", "sync_ref", "consent_ref", "window_ref"])
def test_each_current_proof_is_required_in_the_external_epoch(lab, missing):
    make, authority, _, _, _, _ = lab
    session = make()
    session.begin(authority.tokens["recoverer"])
    reconcile_all(session, authority)
    authority.seed_current_proofs(authority.tokens["verifier"], missing=missing)
    with pytest.raises(RecoveryClosed):
        session.release(authority.tokens["approver"])


def test_write_ahead_survives_crash_and_keeps_unknown_without_new_key(lab):
    session = release_lab(lab)
    make, authority, _, _, _, _ = lab
    item = InventoryItem("synthetic-external-only-intent", str(uuid4()), "synthetic-bound-request")
    session.record_possible_submission(item)
    # No HTTP exists; crash now conservatively means potentially submitted.
    restarted = make()
    state = restarted.begin(authority.tokens["recoverer"])
    orphan = next(i for i in state.inventory if i.intent_id == item.intent_id)
    assert orphan.submission_key == item.submission_key and orphan.outcome == "unknown"
    assert orphan.evidence_ref is None
    authority.seed_current_proofs(authority.tokens["verifier"])
    with pytest.raises(RecoveryClosed):
        restarted.release(authority.tokens["approver"])
    assert not restarted.readiness()["operational_egress"]


def test_missing_snapshot_does_not_create_a_database(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        snapshot_inventory(missing)
    assert not missing.exists()
