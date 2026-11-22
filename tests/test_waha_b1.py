"""Offline fixtures only. No real OpenAI call or WhatsApp delivery is claimed."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import replace
from pathlib import Path
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.conversation_context import ConversationContextBuilder, ConversationContextLimits
from rj_studio_ai.domain import InboundMessage, OutboundMessage
from rj_studio_ai.evaluation.suite import fixture_decision
from rj_studio_ai.generation import (
    GeneratedReply,
    GenerationFailure,
    GenerationMetric,
    GenerationTimeout,
)
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    ProviderWebhookRequest,
)
from rj_studio_ai.providers.waha import WahaAdapter, WahaAPI, WahaTextSender
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository
from rj_studio_ai.waha_live import WahaSettings, build_waha_pipeline, create_waha_app
from rj_studio_ai.waha_safety import WahaConversationStore, WahaSafetyError, WahaSafetyJournal

SECONDARY, PARTICIPANT = "+15550000001", "+15550000002"
CHAT, CHANNEL = "15550000002@c.us", "15550000001@c.us"
KEY = secrets.token_urlsafe(32)


def settings(path, **overrides):
    values = dict(
        _env_file=None,
        waha_secondary_phone=SECONDARY,
        waha_authorized_phones=(PARTICIPANT,),
        waha_webhook_secret=KEY,
        waha_operator_token=KEY,
        waha_api_key=KEY,
        waha_journal_key=KEY,
        waha_state_path=path / "state/conversations.db",
        waha_control_path=path / "control",
        waha_witness_path=path / "witness/head.json",
        salon_knowledge_path=Path("knowledge/rj_studio.yaml"),
    )
    return WahaSettings(**(values | overrides))


def journal(path):
    return WahaSafetyJournal(
        path / "control", path / "witness/head.json", key=KEY, scope={"fixture": True}
    )


def envelope(body="Oi", identifier="ONE"):
    now = int(time.time())
    return {
        "id": "evt_" + identifier,
        "timestamp": now * 1000,
        "session": "default",
        "engine": "WEBJS",
        "me": {"id": CHANNEL},
        "event": "message",
        "payload": {
            "id": "false_" + CHAT + "_" + identifier,
            "timestamp": now,
            "from": CHAT,
            "to": CHANNEL,
            "fromMe": False,
            "body": body,
            "participant": None,
            "hasMedia": False,
            "_data": {"type": "chat"},
        },
    }


def request(raw):
    body = json.dumps(raw).encode()
    return ProviderWebhookRequest(
        "POST",
        "http://private.invalid",
        {
            "x-webhook-hmac": hmac.new(KEY.encode(), body, hashlib.sha512).hexdigest(),
            "x-webhook-hmac-algorithm": "sha512",
            "content-type": "application/json",
        },
        b"",
        "application/json",
        body,
    )


def adapter():
    return WahaAdapter(
        secret=KEY, secondary=SECONDARY, participants=(PARTICIPANT,), clock=time.time
    )


def test_authentication_wire_and_timestamp():
    req = request(envelope())
    assert len(adapter().receive(req).events) == 1
    with pytest.raises(InvalidWebhookSignature):
        adapter().receive(replace(req, body=req.body + b" "))
    old = envelope()
    old["timestamp"] -= 301_000
    with pytest.raises(InvalidWebhookPayload):
        adapter().receive(request(old))


@pytest.mark.parametrize(
    "changes",
    [
        {"fromMe": True},
        {"from": "15550000003@c.us"},
        {"from": "group@g.us"},
        {"from": "status@broadcast"},
        {"participant": "someone@c.us"},
        {"hasMedia": True},
        {"to": "another@c.us"},
        {"_data": {"type": "image"}},
    ],
)
def test_outside_text_allowlist_is_ignored(changes):
    raw = envelope()
    raw["payload"].update(changes)
    assert adapter().receive(request(raw)).events == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"session": "other"},
        {"me": {"id": "other@c.us"}},
        {"engine": "NOWEB"},
    ],
)
def test_wrong_session_account_engine_fail_closed(changes):
    with pytest.raises(InvalidWebhookPayload):
        adapter().receive(request(envelope() | changes))


def test_lid_requires_verified_alias_and_canonicalizes_dedupe_identity():
    lid = "123456789012345@lid"
    raw = envelope()
    raw["payload"]["from"] = lid
    raw["payload"]["id"] = "false_" + lid + "_ONE"
    channel = adapter()
    assert channel.receive(request(raw)).events == ()
    channel.bind_verified_identities({lid: CHAT})
    event = channel.receive(request(raw)).events[0]
    assert event.customer_address == CHAT
    assert event.provider_message_id == "false_" + CHAT + "_ONE"
    assert event.metadata.message_aliases[0].message_id == "false_" + lid + "_ONE"
    with pytest.raises(ValueError):
        channel.bind_verified_identities({lid: "outside@c.us"})


def test_only_explicit_contact_check_can_supply_brazil_phone_alias():
    paths = []

    def handler(req):
        paths.append(str(req.url))
        return httpx.Response(200, json={"numberExists": True, "chatId": "123456@lid", "pn": CHAT})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        api = WahaAPI(base_url="http://127.0.0.1:3000", api_key=KEY, client=client)
        assert api.identities_for(PARTICIPANT) == {CHAT, "123456@lid"}
    assert len(paths) == 1 and "/api/contacts/check-exists?phone=" in paths[0]


def test_contact_lookup_allows_verified_response_after_two_seconds():
    def slow_contact(req):
        # Reproduce the real call-site failure without a wall-clock sleep.
        if req.extensions["timeout"]["read"] < 6.89:
            raise httpx.ReadTimeout("fixture_slow_contact", request=req)
        assert req.extensions["timeout"]["read"] == 20
        return httpx.Response(200, json={"numberExists": True, "chatId": "123456@lid"})

    with httpx.Client(transport=httpx.MockTransport(slow_contact)) as client:
        api = WahaAPI(base_url="http://127.0.0.1:3000", api_key=KEY, client=client)
        assert api.identities_for(PARTICIPANT) == {CHAT, "123456@lid"}


def test_duplicate_persisted_once_runtime_never_authorizes(tmp_path):
    _, safety, store, _, generator, _, _ = build_waha_pipeline(settings(tmp_path))
    try:
        event = adapter().receive(request(envelope())).events[0]
        for _ in range(2):
            store.record_webhook_events((event,), require_message_provenance=True)
        assert len(store.get_history(provider="waha", customer_address=CHAT)) == 1
        assert not generator.is_configured()
        assert not store.authorize_delivery_submission(delivery_id=1, owner_token="fixture")
        assert not store.authorize_legacy_reply(message=event)
        assert not store.authorize_waha_http(None)
    finally:
        safety.close()


def test_journal_single_root_restore_denied(tmp_path):
    safety = journal(tmp_path)
    before = safety.path.read_bytes()
    safety.change("resume")
    safety.path.write_bytes(before)
    try:
        with pytest.raises(WahaSafetyError):
            safety.refresh()
    finally:
        safety.close()


def test_database_restore_cannot_erase_pause_or_consent(tmp_path):
    safety = journal(tmp_path)
    path = tmp_path / "db.sqlite"
    store = WahaConversationStore(path, journal=safety)
    store.initialize()
    try:
        with sqlite3.connect(path) as source, sqlite3.connect(tmp_path / "old.sqlite") as target:
            source.backup(target)
        event = adapter().receive(request(envelope())).events[0]
        store.record_webhook_events((event,), require_message_provenance=True)
        safety.change("revoke", CHAT)
        with sqlite3.connect(tmp_path / "old.sqlite") as source, sqlite3.connect(path) as target:
            source.backup(target)
        with pytest.raises(WahaSafetyError, match="database_restore"):
            store.get_generation(provider="waha", provider_message_id=event.provider_message_id)
        assert not store.authorize_waha_http(None)
    finally:
        safety.close()


def test_restart_pauses_retains_budget_revocation(tmp_path):
    safety = journal(tmp_path)
    store = WahaConversationStore(tmp_path / "db.sqlite", journal=safety)
    store.initialize()
    safety.change("resume")
    safety.reserve(input_tokens=100, output_tokens=10)
    safety.settle(known=True)
    safety.change("revoke", CHAT)
    safety.close()
    fresh = journal(tmp_path)
    try:
        recovered = WahaConversationStore(tmp_path / "db.sqlite", journal=fresh)
        recovered.initialize()
        assert fresh.paused and fresh.calls == 1 and fresh.reserved_tokens == 110
        fresh.change("resume")
        assert not fresh.permits_generation(CHAT)
        assert not recovered.authorize_delivery_submission(delivery_id=1, owner_token="fixture")
    finally:
        fresh.close()


def test_unknown_spend_cannot_retry_after_restart(tmp_path):
    safety = journal(tmp_path)
    safety.change("resume")
    safety.reserve(input_tokens=100, output_tokens=10)
    safety.settle(known=False)
    safety.close()
    fresh = journal(tmp_path)
    try:
        fresh.change("resume")
        with pytest.raises(GenerationFailure):
            fresh.reserve(input_tokens=100, output_tokens=10)
    finally:
        fresh.close()


def test_twenty_calls_and_token_cost_caps(tmp_path):
    safety = journal(tmp_path)
    safety.change("resume")
    try:
        with pytest.raises(GenerationFailure):
            safety.reserve(input_tokens=500_001, output_tokens=1)
        for _ in range(20):
            safety.reserve(input_tokens=1, output_tokens=1)
            safety.settle(known=True)
        with pytest.raises(GenerationFailure):
            safety.reserve(input_tokens=1, output_tokens=1)
    finally:
        safety.close()


def test_incomplete_commit_and_missing_witness_deny(tmp_path):
    safety = journal(tmp_path)
    safety.append({"kind": "prepare", "digest": "fixture"})
    safety.close()
    safety = journal(tmp_path)
    try:
        with pytest.raises(WahaSafetyError):
            safety.refresh()
    finally:
        safety.close()
    (tmp_path / "witness/head.json").unlink()
    with pytest.raises(WahaSafetyError):
        journal(tmp_path)


class FixtureGenerator:
    def __init__(self, entered, release):
        self.entered, self.release = entered, release

    def is_configured(self):
        return True

    def generate(self, message, *, context, remaining_budget):
        self.entered.set()
        assert self.release.wait(3)
        decision = fixture_decision(
            surface="agentic",
            intents=["greeting"],
            reply_parts=[
                {
                    "kind": "conversation",
                    "purpose": "social",
                    "text": "Oi! Como posso te ajudar?",
                    "targets": [],
                }
            ],
        )
        return GeneratedReply(
            decision,
            GenerationMetric(
                provider="openai",
                model="gpt-6.1-sol",
                configuration="OFFLINE_FIXTURE",
                latency_ms=1,
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                estimated_cost_microusd=None,
                outcome="success",
                error_code=None,
            ),
        )


def test_ack_before_model_and_dedupe(tmp_path, monkeypatch):
    entered, release = Event(), Event()
    monkeypatch.setattr(
        "rj_studio_ai.waha_live.generator_from_settings",
        lambda _: FixtureGenerator(entered, release),
    )
    app = create_waha_app(settings(tmp_path))
    with TestClient(app) as client:
        app.state.journal.change("resume")
        req = request(envelope())
        started = time.monotonic()
        assert (
            client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code == 204
        )
        assert time.monotonic() - started < 1
        assert entered.wait(1)
        assert (
            client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code == 204
        )
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            lifecycle = app.state.store.get_generation(
                provider="waha", provider_message_id=envelope()["payload"]["id"]
            )
            if lifecycle.state.value == "completed":
                break
            time.sleep(0.02)
        assert lifecycle.state.value == "completed" and app.state.journal.calls == 1
        assert app.state.outbound_executor is None
        delivery = app.state.store.get_delivery_for_provider_inbound(
            provider="waha", provider_message_id=envelope()["payload"]["id"]
        )
        assert delivery.state is DeliveryState.PENDING


def test_revocation_disconnect_and_operator_auth(tmp_path):
    app = create_waha_app(settings(tmp_path))
    with TestClient(app) as client:
        req = request(envelope("pare"))
        assert (
            client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code == 204
        )
        app.state.journal.change("resume")
        assert not app.state.journal.permits_generation(CHAT)
        assert client.post("/ops/resume").status_code == 403
        assert client.get("/ready").status_code == 403
        assert (
            client.post("/ops/resume", headers={"Authorization": "Bearer " + KEY}).status_code
            == 409
        )
        req = request(envelope() | {"event": "session.status", "payload": {"status": "STOPPED"}})
        assert (
            client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code == 204
        )
        assert app.state.journal.paused


@pytest.mark.parametrize("outcome", ["timeout", "http500", "invalid", "accepted", "disconnected"])
def test_transport_fixture_unknown_never_retries(outcome):
    calls = []

    def handler(req):
        calls.append(req)
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "status": "STOPPED" if outcome == "disconnected" else "WORKING",
                    "me": {"id": CHANNEL},
                },
            )
        if outcome == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if outcome == "http500":
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={}
            if outcome == "invalid"
            else {"id": "true_" + CHAT + "_FIXTURE", "fromMe": True, "to": CHAT},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        sender = WahaTextSender(
            api=WahaAPI(base_url="http://127.0.0.1:3000", api_key=KEY, client=client),
            secondary=SECONDARY,
            participants=(PARTICIPANT,),
            authorize_http=lambda _: True,
        )
        msg = OutboundMessage(CHANNEL, CHAT, "Explicit fixture", submission_key="synthetic")
        if outcome == "accepted":
            assert sender.send(msg, timeout_seconds=1).provider_message_id.endswith("FIXTURE")
        else:
            with pytest.raises(
                OutboundPermanentError if outcome == "disconnected" else OutboundOutcomeUnknown
            ):
                sender.send(msg, timeout_seconds=1)
    assert sum(req.method == "POST" for req in calls) == (outcome != "disconnected")


def test_real_knowledge_canonical_history_after_restart(tmp_path):
    # ACCEPTED_LEGACY below is an explicit offline delivery fixture.
    path = tmp_path / "core.sqlite"
    store = SqliteConversationStore(path)
    store.initialize()
    first = InboundMessage("fixture", "one", "customer", "channel", "Quero progressiva")
    claim = store.claim_generation(first)
    store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="fixture",
        delivery_state=DeliveryState.ACCEPTED_LEGACY,
    )
    store = SqliteConversationStore(path)
    store.initialize()
    second = replace(first, provider_message_id="two", body="Meu cabelo é médio. E quanto fica?")
    lifecycle = store.admit_generation(second)
    knowledge = SalonKnowledgeRepository(Path("knowledge/rj_studio.yaml"))
    assert len(knowledge.load()) == 22
    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=knowledge,
        limits=ConversationContextLimits(use_history_for_knowledge=True),
    ).build(inbound_message_id=lifecycle.inbound_message_id, current_body=second.body)
    assert "R$ 200,00" in next(
        f.statement for f in context.knowledge if f.id == "precos-progressiva"
    )
    assert context.history[0].body == "Quero progressiva"


def test_model_timeout_blocks_unknown_spend_without_another_api_call(tmp_path, monkeypatch):
    calls = []

    class TimeoutFixture:
        def is_configured(self):
            return True

        def generate(self, *args, **kwargs):
            calls.append(1)
            raise GenerationTimeout("provider_timeout")

    monkeypatch.setattr(
        "rj_studio_ai.waha_live.generator_from_settings", lambda _: TimeoutFixture()
    )
    _, safety, store, _, _, _, runner = build_waha_pipeline(settings(tmp_path))
    try:
        safety.change("resume")
        event = adapter().receive(request(envelope())).events[0]
        store.record_webhook_events((event,), require_message_provenance=True)
        result = runner.run_once()
        assert result is None
        assert len(calls) == 1 and safety.unresolved
        assert runner.run_once() is None
        assert len(calls) == 1
        assert not store.authorize_waha_http(None)
    finally:
        safety.close()


def test_human_request_uses_core_and_suppresses_following_turn(tmp_path, monkeypatch):
    class HumanFixture:
        def is_configured(self):
            return True

        def generate(self, *args, **kwargs):
            return GeneratedReply(
                fixture_decision(
                    intents=["human_request"],
                    handoff=True,
                    handoff_reason="explicit_human_request",
                ),
                GenerationMetric(
                    provider="openai",
                    model="gpt-6.1-sol",
                    configuration="OFFLINE_FIXTURE",
                    latency_ms=1,
                    input_tokens=10,
                    output_tokens=10,
                    total_tokens=20,
                    estimated_cost_microusd=None,
                    outcome="success",
                    error_code=None,
                ),
            )

    monkeypatch.setattr("rj_studio_ai.waha_live.generator_from_settings", lambda _: HumanFixture())
    _, safety, store, _, _, _, runner = build_waha_pipeline(settings(tmp_path))
    try:
        safety.change("resume")
        first = adapter().receive(request(envelope("Quero falar com uma pessoa"))).events[0]
        store.record_webhook_events((first,), require_message_provenance=True)
        assert runner.run_once().state.value == "completed"
        assert store.list_active_handoffs()[0].reason_code.value == "explicit_human_request"
        second = adapter().receive(request(envelope("Oi de novo", "TWO"))).events[0]
        store.record_webhook_events((second,), require_message_provenance=True)
        assert (
            store.get_generation(
                provider="waha", provider_message_id=second.provider_message_id
            ).state.value
            == "suppressed"
        )
        assert safety.calls == 1
    finally:
        safety.close()
