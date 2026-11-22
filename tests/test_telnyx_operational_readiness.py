"""Operational permission races. Synthetic facts; real SQLite serialization."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import TIME
from test_telnyx_messages import ingress as ingress
from test_telnyx_submission import authorize, prepare

from rj_studio_ai.persistence import SqliteConversationStore


@pytest.mark.parametrize("revoke_first", [True, False])
def test_consent_revocation_and_authorization_have_explicit_commit_order(ingress, revoke_first):
    store, path, claim = prepare(ingress)
    revocation_locked, authorization_started, release = Event(), Event(), Event()

    def revoke():
        if not revoke_first:
            assert authorization_started.wait(5)
        with store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE telnyx_consent SET revoked_at=?", (TIME.isoformat(),))
            revocation_locked.set()
            if revoke_first:
                assert release.wait(5)

    def authorize_peer():
        if revoke_first:
            assert revocation_locked.wait(5)
        authorization_started.set()
        allowed = authorize(SqliteConversationStore(path), claim)
        if not revoke_first:
            # Revoker may commit only after authorization transaction returns.
            authorization_returned.set()
        return allowed

    authorization_returned = Event()
    if not revoke_first:
        # Make this ordering explicit rather than depending on scheduler timing.
        original_revoke = revoke

        def revoke():
            assert authorization_returned.wait(5)
            return original_revoke()

    with ThreadPoolExecutor(max_workers=2) as pool:
        revoker = pool.submit(revoke)
        authorizer = pool.submit(authorize_peer)
        if revoke_first:
            assert authorization_started.wait(5)
            release.set()
        revoker.result(10)
        allowed = authorizer.result(10)
    assert allowed is (not revoke_first)
    assert store.get_delivery(claim.delivery_id).first_submission_at == (
        None if revoke_first else TIME
    )
    assert not authorize(store, claim)
    # This test deliberately performs no exchange: marker-first may be in flight
    # in a future integration and cannot promise an external recall.
