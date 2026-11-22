"""Python -> stdio -> real workerd/DO; WAHA and intelligence are explicit fixtures.

The Node child needs local loopback for Miniflare, never external credentials.
CI runs this file in its separate Worker job, with Python IP sockets blocked.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import replace
from threading import Event

import httpx
import pytest
from test_waha_b1 import CHAT, KEY, FixtureGenerator, envelope, request, settings

from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.persistence import DeliveryState
from rj_studio_ai.providers.waha import WahaAPI
from rj_studio_ai.waha_authority import AuthorityClosed, AuthorityConfig, CloudflareAuthority
from rj_studio_ai.waha_cloudflare import (
    AnchoredWahaJournal,
    AuthorizedWahaSender,
    CloudflareWahaStore,
)
from rj_studio_ai.waha_live import build_waha_pipeline


class Bridge:
    def __init__(self, scope):
        env = {
            "PATH": os.environ["PATH"],
            "HOME": os.environ["HOME"],
            "LIVIA_FIXTURE_SCOPE": scope,
            "LIVIA_FIXTURE_PARTICIPANT": hashlib.sha256(CHAT.encode()).hexdigest(),
        }
        self.process = subprocess.Popen(
            [
                os.environ.get("LIVIA_TEST_NODE") or shutil.which("node"),
                "infra/waha-authority/test/bridge.mjs",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        line = self.process.stdout.readline()
        assert line, self.process.stderr.read()
        ready = json.loads(line)
        self.config = AuthorityConfig(**ready["config"])
        self.operator = ready["operator"]

    def exchange(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()
        result = json.loads(self.process.stdout.readline())
        assert "bridge_error" not in result, result
        return result

    def transport(self, request):
        result = self.exchange({"body": request.content.decode(), "headers": dict(request.headers)})
        return httpx.Response(result["status"], text=result["body"])

    def close(self):
        self.process.stdin.write('{"action":"close"}\n')
        self.process.stdin.flush()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
            raise
        assert self.process.returncode == 0, self.process.stderr.read()


@pytest.fixture
def live_protocol(tmp_path, monkeypatch):
    released = Event()
    released.set()
    monkeypatch.setattr(
        "rj_studio_ai.waha_live.generator_from_settings",
        lambda _: FixtureGenerator(Event(), released),
    )
    configured = settings(tmp_path)
    _, original, _, _, _, _, _ = build_waha_pipeline(configured)
    scope, head, sequence = original.scope, original.head, len(original.entries)
    original.close()
    bridge = Bridge(scope)
    client = httpx.Client(transport=httpx.MockTransport(bridge.transport))
    authority = CloudflareAuthority(bridge.config, client=client)
    authority.command(
        "initialize", {"head": head, "sequence": sequence}, operator_key=bridge.operator
    )

    def journal(*args, **kwargs):
        return AnchoredWahaJournal(*args, authority=authority, **kwargs)

    adapter, safety, store, _, _, context, runner = build_waha_pipeline(
        configured, journal_factory=journal, store_factory=CloudflareWahaStore
    )
    safety.change("resume")
    event = adapter.receive(request(envelope())).events[0]
    store.record_webhook_events((event,), require_message_provenance=True)
    runner.run_once()
    identity = store.logical_identity(event.provider_message_id, adapter.secondary)

    def release():
        authority.current()
        return authority.command(
            "release",
            {
                "boot": authority.boot_id,
                "epoch": authority.epoch,
                "head": safety.head,
                "intent": identity,
                "participant": store.participant_identity(CHAT),
                "expires_at": int(time.time() * 1000) + 60000,
            },
            operator_key=bridge.operator,
        )

    try:
        yield adapter, safety, store, authority, bridge, release, context
    finally:
        if not safety.lockfile.closed:
            safety.close()
        client.close()
        bridge.close()


def sender(adapter, store, outcome="accepted"):
    posts = []

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"status": "WORKING", "me": {"id": adapter.secondary}})
        posts.append(req.content)
        wire = json.loads(req.content)
        assert wire["chatId"] == CHAT and wire["session"] == "default"
        if outcome == "timeout":
            raise httpx.ReadTimeout("fixture_ambiguous", request=req)
        if outcome == "http500":
            return httpx.Response(500)
        return httpx.Response(
            201,
            json={
                "fromMe": True,
                "to": CHAT,
                "id": "true_" + CHAT + "_FIXTURE" if outcome == "accepted" else "invalid",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = WahaAPI(base_url="http://waha:3000", api_key=KEY, client=client)
    result = OutboundDeliveryRunner(
        store=store,
        sender=AuthorizedWahaSender(store, api, adapter),
        timeout_seconds=1,
        provider="waha",
        maximum_attempts=1,
    )
    return result, client, posts


def test_signed_cloudflare_protocol_to_canonical_outbox_acceptance(live_protocol):
    adapter, safety, store, authority, _, release, context = live_protocol
    release()
    runner, client, posts = sender(adapter, store)
    with client:
        result = runner.run_once()
        assert result.state is DeliveryState.ACCEPTED
        assert len(posts) == 1
        assert runner.run_once() is None
    assert list(authority.current()["intents"].values())[0]["outcome"] == "accepted"
    assert not store.authorize_legacy_reply(delivery_id=result.delivery_id)
    assert not store.authorize_waha_http(None)
    assert safety.calls == 1


@pytest.mark.parametrize("outcome", ["timeout", "http500", "invalid"])
def test_ambiguous_acceptance_never_retries(live_protocol, outcome):
    adapter, _, store, authority, _, release, _ = live_protocol
    release()
    runner, client, posts = sender(adapter, store, outcome)
    with client:
        result = runner.run_once()
        assert result.state is DeliveryState.UNKNOWN
        assert runner.run_once() is None
        assert len(posts) == 1
    assert list(authority.current()["intents"].values())[0]["outcome"] == "unknown"
    with pytest.raises(AuthorityClosed, match="unresolved_submission"):
        release()


@pytest.mark.parametrize("control", ["pause", "revoke", "kill"])
def test_control_after_claim_denies_provider_http(live_protocol, control):
    adapter, safety, store, authority, bridge, release, _ = live_protocol
    release()
    claim = store.claim_next_delivery(provider="waha")
    if control == "kill":
        authority.command("kill", {}, operator_key=bridge.operator)
    else:
        safety.change(control, CHAT if control == "revoke" else None)
    from rj_studio_ai.domain import OutboundMessage

    message = OutboundMessage(
        claim.provider_channel_id, CHAT, claim.body, submission_key=claim.submission_key
    )
    with pytest.raises(AuthorityClosed):
        store.authorize_delivery_submission(
            delivery_id=claim.delivery_id, owner_token=claim.owner_token, message=message
        )
    assert not authority.current()["intents"]


def test_authority_restore_cannot_erase_pending_submission(live_protocol):
    adapter, _, store, authority, bridge, release, _ = live_protocol
    release()
    old = bridge.exchange({"action": "snapshot"})["value"]
    runner, client, posts = sender(adapter, store, "timeout")
    with client:
        assert runner.run_once().state is DeliveryState.UNKNOWN
    bridge.exchange({"action": "restore", "value": old})
    with pytest.raises(AuthorityClosed):
        authority.current()
    assert len(posts) == 1
    assert store.claim_next_delivery(provider="waha") is None


def test_same_account_configuration_rejected_before_http():
    with pytest.raises(ValueError, match="independent_authority"):
        AuthorityConfig(
            url="https://fixture.example.workers.dev/command",
            scope="a" * 64,
            account="1" * 32,
            witness_account="1" * 32,
            public_key="b" * 64,
            runtime_key=KEY,
        )


def test_signed_response_with_another_public_key_is_not_accepted(live_protocol):
    _, _, _, authority, _, _, _ = live_protocol
    wrong = CloudflareAuthority(
        replace(authority.config, public_key="0" * 64), client=authority.client
    )
    with pytest.raises(AuthorityClosed, match="authority_response_unverified"):
        wrong.read()


def test_global_local_restore_cannot_replay_a_consumed_identity(live_protocol, tmp_path):
    adapter, safety, store, authority, _, release, _ = live_protocol
    old_journal = safety.path.read_bytes()
    old_witness = safety.witness.read_bytes()
    old_database = tmp_path / "old.db"
    with sqlite3.connect(store._database_path) as source, sqlite3.connect(old_database) as target:
        source.backup(target)
    release()
    runner, client, posts = sender(adapter, store)
    with client:
        assert runner.run_once().state is DeliveryState.ACCEPTED
    safety.close()
    safety.path.write_bytes(old_journal)
    safety.witness.write_bytes(old_witness)
    with sqlite3.connect(old_database) as source, sqlite3.connect(store._database_path) as target:
        source.backup(target)
    new_authority = CloudflareAuthority(authority.config, client=authority.client)
    with pytest.raises(AuthorityClosed, match="local_restore_or_boot_invalid"):
        build_waha_pipeline(
            settings(tmp_path),
            journal_factory=lambda *args, **kwargs: AnchoredWahaJournal(
                *args, authority=new_authority, **kwargs
            ),
            store_factory=CloudflareWahaStore,
        )
    assert len(posts) == 1


def test_canonical_memory_only_admits_provider_accepted_fixture_reply(live_protocol):
    adapter, _, store, _, _, release, context = live_protocol
    release()
    runner, client, _ = sender(adapter, store)
    with client:
        assert runner.run_once().state is DeliveryState.ACCEPTED
    event = adapter.receive(request(envelope("Meu cabelo é médio", "SECOND"))).events[0]
    store.record_webhook_events((event,), require_message_provenance=True)
    lifecycle = store.get_generation(provider="waha", provider_message_id=event.provider_message_id)
    built = context.build(inbound_message_id=lifecycle.inbound_message_id, current_body=event.body)
    assert any(turn.role == "ai_attendant" for turn in built.history)
    assert any(turn.role == "customer" and turn.body == "Oi" for turn in built.history)


def test_kill_after_external_marker_denies_the_only_transport_ticket(live_protocol):
    adapter, _, store, authority, bridge, release, _ = live_protocol
    from rj_studio_ai.domain import OutboundMessage
    from rj_studio_ai.providers.base import OutboundOutcomeUnknown

    release()
    claim = store.claim_next_delivery(provider="waha")
    message = OutboundMessage(
        claim.provider_channel_id, CHAT, claim.body, submission_key=claim.submission_key
    )
    assert store.authorize_delivery_submission(
        delivery_id=claim.delivery_id, owner_token=claim.owner_token, message=message
    )
    authority.command("kill", {}, operator_key=bridge.operator)
    _, client, posts = sender(adapter, store)
    with client, pytest.raises(OutboundOutcomeUnknown):
        AuthorizedWahaSender(
            store, WahaAPI(base_url="http://waha:3000", api_key=KEY, client=client), adapter
        ).send(message, timeout_seconds=1)
    assert posts == []


def test_replayed_signed_response_does_not_match_a_new_challenge(live_protocol):
    _, _, _, authority, bridge, _, _ = live_protocol
    captured = []

    def transport(req):
        if not captured:
            response = bridge.transport(req)
            captured.append(response.content)
        return httpx.Response(200, content=captured[0])

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        other = CloudflareAuthority(authority.config, client=client)
        assert other.read()
        with pytest.raises(AuthorityClosed, match="authority_response_unverified"):
            other.read()


def test_grant_for_other_intent_does_not_claim_pending_reply(live_protocol):
    adapter, safety, store, authority, bridge, _, _ = live_protocol
    authority.current()
    authority.command(
        "release",
        {
            "boot": authority.boot_id,
            "epoch": authority.epoch,
            "head": safety.head,
            "intent": "0" * 64,
            "participant": store.participant_identity(CHAT),
            "expires_at": int(time.time() * 1000) + 60000,
        },
        operator_key=bridge.operator,
    )
    assert store.claim_next_delivery(provider="waha") is None
    delivery = store.get_delivery_for_provider_inbound(
        provider="waha", provider_message_id=envelope()["payload"]["id"]
    )
    assert delivery.state is DeliveryState.PENDING and delivery.attempt_count == 0


def test_expired_grant_does_not_claim_pending_reply(live_protocol):
    _, safety, store, authority, bridge, _, _ = live_protocol
    authority.command(
        "release",
        {
            "boot": authority.boot_id,
            "epoch": authority.epoch,
            "head": safety.head,
            "intent": store.logical_identity(envelope()["payload"]["id"], envelope()["me"]["id"]),
            "participant": store.participant_identity(CHAT),
            "expires_at": int(time.time() * 1000) + 200,
        },
        operator_key=bridge.operator,
    )
    time.sleep(0.25)
    assert store.claim_next_delivery(provider="waha") is None


def test_unknown_reconciliation_rechecks_provider_fact_and_restores_ordering(live_protocol):
    from rj_studio_ai.domain import OutboundMessage
    from rj_studio_ai.waha_cloudflare import observe_waha_acceptance

    adapter, _, store, authority, bridge, release, _ = live_protocol
    release()
    runner, client, posts = sender(adapter, store, "timeout")
    with client:
        result = runner.run_once()
    assert result.state is DeliveryState.UNKNOWN
    # Migration 0024 must preserve both terminal guards without an immutable proof.
    with store._connect() as connection:
        for statement in (
            "UPDATE outbound_deliveries SET state='accepted',provider_message_id='unproven' "
            "WHERE id=?",
            "UPDATE delivery_attempts SET outcome='accepted',provider_message_id='unproven' "
            "WHERE outbound_delivery_id=?",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, (result.delivery_id,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO waha_reconciliation_evidence VALUES(?,?,?,?,?,?,?)",
                (result.delivery_id, "a" * 64, "unproven", "b" * 64, 1, "c" * 64, "fixture"),
            )
    identity, entry = next(iter(authority.current()["intents"].items()))
    provider_id = "true_" + CHAT + "_OBSERVED"
    wire = json.loads(posts[0])
    message = OutboundMessage(adapter.secondary, CHAT, wire["text"], submission_key=entry["key"])

    def provider(req):
        if req.url.path.endswith("/api/sessions/default"):
            return httpx.Response(200, json={"status": "WORKING", "me": {"id": adapter.secondary}})
        return httpx.Response(
            200,
            json={
                "id": provider_id,
                "fromMe": True,
                "hasMedia": False,
                "body": wire["text"],
                "to": CHAT,
                "ack": 2,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(provider)) as proof_client:
        proof_api = WahaAPI(base_url="http://waha:3000", api_key=KEY, client=proof_client)
        evidence = observe_waha_acceptance(
            proof_api, adapter.identity_aliases, message, provider_id
        )
        authority.command(
            "reconcile",
            {
                "intent": identity,
                "token": entry["token"],
                "digest": entry["digest"],
                "outcome": "accepted",
                "acceptance": hashlib.sha256(provider_id.encode()).hexdigest(),
                "evidence": evidence,
            },
            operator_key=bridge.operator,
        )
        assert store.reconcile_provider_message(
            identity, provider_id, api=proof_api, aliases=adapter.identity_aliases
        )
    assert store.get_delivery(result.delivery_id).state is DeliveryState.ACCEPTED
    assert len(posts) == 1
    with store._connect() as connection:
        for statement in (
            "UPDATE waha_reconciliation_evidence SET authority_revision=999",
            "DELETE FROM waha_reconciliation_evidence",
            "UPDATE outbound_deliveries SET state='pending' WHERE id=?",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, (result.delivery_id,) if "?" in statement else ())
    assert authority.current()["paused"]


def test_failed_control_anchor_is_sticky_until_independent_recovery(live_protocol, monkeypatch):
    _, safety, store, authority, _, release, _ = live_protocol
    release()

    def failed(*args, **kwargs):
        raise AuthorityClosed("fixture_external_outage")

    monkeypatch.setattr(authority, "advance", failed)
    with pytest.raises(AuthorityClosed):
        safety.change("revoke", CHAT)
    assert safety.fault_path.exists()
    with pytest.raises(AuthorityClosed, match="anchoring_fault_requires_operator_recovery"):
        safety.refresh()
    with pytest.raises(AuthorityClosed):
        store.claim_next_delivery(provider="waha")


def test_provider_reconciliation_rejects_unverified_facts_without_new_submission(live_protocol):
    from rj_studio_ai.domain import OutboundMessage
    from rj_studio_ai.waha_cloudflare import observe_waha_acceptance

    adapter, _, store, authority, _, release, _ = live_protocol
    release()
    runner, client, posts = sender(adapter, store, "timeout")
    with client:
        result = runner.run_once()
    identity, entry = next(iter(authority.current()["intents"].items()))
    provider_id = "true_" + CHAT + "_OBSERVED"
    message = OutboundMessage(
        adapter.secondary, CHAT, json.loads(posts[0])["text"], submission_key=entry["key"]
    )
    good = {
        "id": provider_id,
        "fromMe": True,
        "hasMedia": False,
        "body": message.body,
        "to": CHAT,
        "ack": 2,
    }
    for alteration in (
        {"body": "another response"},
        {"fromMe": False},
        {"id": "another"},
        {"to": "999@c.us"},
        {"hasMedia": True},
        {"ack": 0},
        {"ack": True},
    ):
        calls = []

        def provider(req, calls=calls, alteration=alteration):
            calls.append(req.method)
            if req.url.path.endswith("/api/sessions/default"):
                return httpx.Response(
                    200, json={"status": "WORKING", "me": {"id": adapter.secondary}}
                )
            return httpx.Response(200, json={**good, **alteration})

        with httpx.Client(transport=httpx.MockTransport(provider)) as proof_client:
            proof_api = WahaAPI(base_url="http://waha:3000", api_key=KEY, client=proof_client)
            with pytest.raises(AuthorityClosed, match="provider_evidence_unverified"):
                observe_waha_acceptance(proof_api, adapter.identity_aliases, message, provider_id)
        assert calls == ["GET", "GET"]
    assert authority.current()["intents"][identity]["outcome"] == "unknown"
    assert store.get_delivery(result.delivery_id).state is DeliveryState.UNKNOWN
    assert len(posts) == 1
