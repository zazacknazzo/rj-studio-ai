"""Temporary accepted-risk mode, real canonical outbox; no external network/model."""

import hashlib
import json
from threading import Event
from time import time

import httpx
import pytest
from test_waha_b1 import CHAT, KEY, FixtureGenerator, envelope, request, settings

from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.persistence import DeliveryState
from rj_studio_ai.providers.waha import WahaAPI
from rj_studio_ai.waha_authority import AuthorityClosed
from rj_studio_ai.waha_cloudflare import AnchoredWahaJournal, AuthorizedWahaSender
from rj_studio_ai.waha_live import build_waha_pipeline
from rj_studio_ai.waha_private_test import LocalTestAuthority, PrivateTestStore


@pytest.fixture
def live(tmp_path, monkeypatch):
    released = Event()
    released.set()
    generator = FixtureGenerator(Event(), released)
    monkeypatch.setattr("rj_studio_ai.waha_live.generator_from_settings", lambda _: generator)
    configured = settings(tmp_path)
    _, old, _, _, _, _, _ = build_waha_pipeline(configured)
    authority = LocalTestAuthority.prepare(
        tmp_path / "ledger.jsonl",
        key=configured.waha_journal_key,
        scope=old.scope,
        head=old.head,
        sequence=len(old.entries),
        participant=hashlib.sha256(CHAT.encode()).hexdigest(),
        deadline=int(time() * 1000) + 3600000,
    )
    old.close()

    def journal(*args, **kwargs):
        return AnchoredWahaJournal(*args, authority=authority, **kwargs)

    adapter, safety, store, _, _, context, processing = build_waha_pipeline(
        configured, journal_factory=journal, store_factory=PrivateTestStore
    )
    safety.change("resume")
    authority.activate()
    posts = []
    outcome = {"value": "accepted"}

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"status": "WORKING", "me": {"id": adapter.secondary}})
        posts.append(json.loads(req.content))
        assert posts[-1]["chatId"] == CHAT
        if outcome["value"] == "timeout":
            raise httpx.ReadTimeout("fixture", request=req)
        if outcome["value"] == "http500":
            return httpx.Response(500)
        identifier = "true_" + CHAT + "_" + str(len(posts))
        response_id = identifier
        if outcome["value"] in ("webjs", "webjs_conflict"):
            response_id = {
                "fromMe": True,
                "remote": CHAT,
                "id": str(len(posts)),
                "_serialized": identifier,
            }
            if outcome["value"] == "webjs_conflict":
                response_id["remote"] = "999@c.us"
        elif outcome["value"] != "accepted":
            response_id = "invalid"
        return httpx.Response(201, json={"fromMe": True, "to": CHAT, "id": response_id})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = WahaAPI(base_url="http://waha:3000", api_key=KEY, client=client)
    delivery = OutboundDeliveryRunner(
        store=store,
        sender=AuthorizedWahaSender(store, api, adapter),
        timeout_seconds=1,
        provider="waha",
        maximum_attempts=1,
    )

    def inbound(identifier="ONE", body="Oi"):
        event = adapter.receive(request(envelope(body, identifier))).events[0]
        store.record_webhook_events((event,), require_message_provenance=True)
        processing.run_once()
        return event

    try:
        yield (
            adapter,
            safety,
            store,
            authority,
            processing,
            delivery,
            inbound,
            posts,
            outcome,
            context,
        )
    finally:
        safety.close()
        client.close()


def test_automatic_two_turns_use_canonical_accepted_memory(live):
    _, _, store, a, _, d, inbound, posts, _, context = live
    event = inbound()
    result = d.run_once()
    assert result.state is DeliveryState.ACCEPTED
    assert d.run_once() is None
    second = inbound("TWO", "Quanto custa?")
    generation = store.get_generation(
        provider="waha", provider_message_id=second.provider_message_id
    )
    built = context.build(
        inbound_message_id=generation.inbound_message_id, current_body=second.body
    )
    assert any(turn.role == "ai_attendant" for turn in built.history)
    assert any(turn.role == "customer" and turn.body == "Oi" for turn in built.history)
    assert d.run_once().state is DeliveryState.ACCEPTED
    assert len(posts) == 2 and len(a.current()["intents"]) == 2
    assert all(i["outcome"] == "accepted" for i in a.current()["intents"].values())
    assert store.get_delivery(result.delivery_id).provider_message_id
    assert event.provider_message_id


@pytest.mark.parametrize("outcome", ["timeout", "http500", "malformed"])
def test_unknown_blocks_every_following_grant_without_retry(live, outcome):
    _, _, _, a, _, d, inbound, posts, result, _ = live
    result["value"] = outcome
    inbound()
    assert d.run_once().state is DeliveryState.UNKNOWN
    assert d.run_once() is None and len(posts) == 1
    with pytest.raises(AuthorityClosed, match="activation_denied"):
        a.activate()


def test_pause_and_wrong_participant_prevent_transport(live):
    _, j, _, a, _, d, inbound, posts, _, _ = live
    inbound()
    with pytest.raises(AuthorityClosed, match="permit_denied"):
        a.permit("a" * 64, "b" * 64, j.head)
    j.change("pause")
    assert d.run_once() is None and posts == []


def test_restart_pauses_and_retains_consumed_inventory(live):
    _, j, _, a, _, d, inbound, posts, _, _ = live
    inbound()
    assert d.run_once().state is DeliveryState.ACCEPTED
    prior = a.current()
    other = LocalTestAuthority(a.path, key=a.key.decode(), scope=a.config.scope)
    other.boot(j.head, len(j.entries))
    assert other.current()["paused"] and not other.current()["enabled"]
    assert other.current()["intents"] == prior["intents"]
    assert other.current()["deadline"] == prior["deadline"]
    with pytest.raises(AuthorityClosed, match="boot_superseded"):
        a.current()
    assert len(posts) == 1


def test_deadline_and_cap_deny_more_work(live):
    _, _, _, a, _, d, inbound, posts, _, _ = live
    inbound()
    a._change(lambda s: s.update(deadline=1))
    assert d.run_once() is None and posts == []
    assert not a.active(
        {
            **a.current(),
            "deadline": time() * 1000 + 1000,
            "intents": {str(i): {"outcome": "accepted"} for i in range(20)},
        }
    )


def test_missing_or_corrupted_ledger_never_bootstraps(live):
    _, _, _, a, _, _, _, _, _, _ = live
    a.path.write_bytes(a.path.read_bytes() + b"broken\n")
    with pytest.raises(AuthorityClosed):
        a.current()
    a.path.unlink()
    with pytest.raises(AuthorityClosed):
        a.current()


@pytest.mark.parametrize(
    "kind,expected", [("webjs", DeliveryState.ACCEPTED), ("webjs_conflict", DeliveryState.UNKNOWN)]
)
def test_actual_webjs_message_id_shape_is_verified(live, kind, expected):
    _, _, _, _, _, d, inbound, posts, outcome, _ = live
    outcome["value"] = kind
    inbound()
    assert d.run_once().state is expected
    assert len(posts) == 1
    assert d.run_once() is None
