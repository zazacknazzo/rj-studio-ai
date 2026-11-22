"""G0 observable vertical slices; run through the existing credential-free runner."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest
from g0_staging_fixture import FACTS, UNTRUSTED_PROSE, G0Staging, decision
from test_telnyx_messages import CUSTOMER, wire
from test_telnyx_submission_migration import backup

from rj_studio_ai.delivery import DeliveryOwnershipLost, OutboundDeliveryRunner
from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.generation import GenerationTimeout
from rj_studio_ai.persistence import DeliveryState, GenerationState, SqliteConversationStore
from rj_studio_ai.telnyx_asgi import create_telnyx_offline_app


@pytest.fixture
def staging(tmp_path):
    return G0Staging(tmp_path)


@pytest.mark.parametrize(
    "scenario,text,proposal,expected",
    [
        ("greeting", "Oi!", decision(), "Oi!"),
        (
            "salon-information",
            "Quais os horários do salão?",
            decision("hours", fact="g0-hours"),
            FACTS["g0-hours"][2],
        ),
        (
            "progressiva",
            "Vocês oferecem progressiva?",
            decision("service_information", fact="g0-progressiva"),
            FACTS["g0-progressiva"][2],
        ),
        (
            "price",
            "Quanto custa a progressiva?",
            decision("price", fact="g0-price"),
            FACTS["g0-price"][2],
        ),
        (
            "appointment-interest",
            "Quero marcar progressiva sábado à tarde",
            decision(
                "appointment_interest",
                appointment_preferences={
                    "desired_service": "progressiva",
                    "preferred_time": "sábado à tarde",
                },
            ),
            "confirmar a disponibilidade",
        ),
        (
            "human-request",
            "Quero falar com uma pessoa",
            decision("human_request", handoff=True, handoff_reason="explicit_human_request"),
            "equipe",
        ),
    ],
    ids=lambda item: item if isinstance(item, str) and len(item) < 25 else None,
)
def test_complete_vertical_slice(staging, scenario, text, proposal, expected):
    s = staging
    envelope = s.inbound(text)
    assert s.rows("messages")[0]["body"] == text
    assert s.rows("inbound_event_receipts")[0]["provider_message_id"] == "g0-inbound-1"
    assert s.rows("outbound_deliveries") == []  # ACK never invokes processing/outbound
    completed = s.process(proposal)
    assert completed.state is GenerationState.COMPLETED
    pending = s.store.get_delivery_for_inbound(completed.inbound_message_id)
    assert pending.state is DeliveryState.PENDING
    assert expected.casefold() in pending.body.casefold()
    assert UNTRUSTED_PROSE not in pending.body and "999" not in pending.body
    accepted = s.deliver()
    assert accepted.state is DeliveryState.ACCEPTED
    request = s.requests[0]
    assert s.signer.prepare(request.message) == request  # exact deterministic bytes
    assert dict(request.headers)["Idempotency-Key"] == accepted.submission_key
    assert json.loads(request.content)["whatsapp_message"]["text"]["body"] == pending.body
    assert s.status(accepted).state is DeliveryState.DELIVERED
    assert s.status(accepted, "read").state is DeliveryState.READ
    assert s.post(envelope).status_code == 204
    assert s.process() is None and s.deliver() is None
    assert len(s.rows("messages")) == 2 and len(s.requests) == 1
    if scenario in {"appointment-interest", "human-request"}:
        assert len(s.store.list_active_handoffs()) == 1
        s.inbound("Mais uma pergunta", identifier="after-handoff")
        assert s.process() is None and s.deliver() is None
        assert s.rows("message_processing")[-1]["state"] == "suppressed"
    if scenario == "appointment-interest":
        intake = s.store.get_appointment_intake(inbound_message_id=completed.inbound_message_id)
        assert intake.state == "handoff" and intake.preferred_time == "sábado à tarde"
        assert "agendei" not in pending.body.casefold()
    s.report(scenario, acceptance_is_not_delivery=True, byte_determinism=True)


def test_multiturn_history_only_includes_provider_accepted_assistant_speech(staging):
    s = staging
    for index, (text, proposal) in enumerate(
        [
            ("Oi!", decision()),
            ("Vocês oferecem progressiva?", decision("service_information", fact="g0-progressiva")),
            ("Quanto custa a progressiva?", decision("price", fact="g0-price")),
        ]
    ):
        s.inbound(text)
        assert s.process(proposal) is not None
        assert len(s.model.contexts[-1].history) == index * 2
        if index:
            assert s.model.contexts[-1].history[-1].role == "ai_attendant"
        delivered = s.status(s.deliver())
        assert delivered.state is DeliveryState.DELIVERED
    assert len(s.store.get_history(provider="telnyx", customer_address=CUSTOMER)) == 6
    s.report("multiturn-history", accepted_assistant_turns_in_next_context=True)


def test_duplicate_before_and_after_restart_never_generates_or_sends_twice(staging):
    s = staging
    envelope = s.inbound("Oi!")
    assert s.post(envelope).status_code == 204
    s.process()
    delivery = s.deliver()
    restarted = SqliteConversationStore(s.path, telnyx_request_signer=s.signer)
    assert (
        OutboundDeliveryRunner(restarted, s.sender, 9, provider="telnyx").run_once(
            now=s.now + timedelta(days=2)
        )
        is None
    )
    assert s.post(envelope).status_code == 204 and s.process() is None
    assert len(s.requests) == len(s.model.contexts) == 1
    assert len(s.rows("inbound_event_receipts")) == 1
    s.status(delivery)
    s.report("duplicate-restart", generation_calls=1)


def test_revocation_after_generation_denies_authorization_without_transport(staging):
    s = staging
    s.inbound("Revogo meu consentimento para mensagens automáticas")
    completed = s.process()
    s.revoke()  # fixture of authoritative update; utterance is NOT an implemented API
    with pytest.raises(DeliveryOwnershipLost):
        s.deliver()
    assert s.requests == [] and s.rows("telnyx_http_requests") == []
    assert (
        s.store.get_delivery_for_inbound(completed.inbound_message_id).first_submission_at is None
    )
    s.report("consent-revocation", consent_capture="synthetic SQL fixture; no live consent API")


def test_optout_text_alone_does_not_persist_consent_revocation(staging):
    s = staging
    s.inbound("Revogo meu consentimento para mensagens automáticas")
    assert s.rows("telnyx_consent")[0]["revoked_at"] is None
    assert not s.requests  # deliberately do not authorize or send this work
    s.report("optout-workflow-gap", gap="no production opt-out capture/revoke workflow")


def test_pause_commits_during_generation_and_suppresses_reply(staging):
    s = staging
    s.inbound("Quero saber sobre progressiva")
    entered, release = Event(), Event()

    def rendezvous():
        entered.set()
        assert release.wait(timeout=10)

    s.model.before_return = rendezvous
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(s.process)
        try:
            assert entered.wait(timeout=10)
            s.inbound("Resposta humana sintética", identifier="pause", kind="echo")
            assert s.rows("conversation_automation_controls")[0]["paused"] == 1
        finally:
            release.set()
        assert future.result(timeout=10) is None
    assert s.rows("outbound_deliveries") == [] and s.requests == []
    s.report("pause-during-generation", pause_source="signed synthetic human echo")


@pytest.mark.parametrize("outcome", ["timeout", "ambiguous"])
def test_unknown_transport_outcome_survives_restart_without_resend(staging, outcome):
    s = staging
    s.inbound("Oi!")
    s.process()
    s.transport_outcome = outcome
    unknown = s.deliver()
    assert unknown.state is DeliveryState.UNKNOWN
    restarted = SqliteConversationStore(s.path, telnyx_request_signer=s.signer)
    for offset in (timedelta(seconds=2), timedelta(days=2)):
        assert (
            OutboundDeliveryRunner(restarted, s.sender, 9, provider="telnyx").run_once(
                now=s.now + offset
            )
            is None
        )
    s.inbound("Outra pergunta", identifier="blocked-by-unknown")
    assert s.process() is None
    assert len(s.requests) == 1
    assert s.store.get_delivery(unknown.delivery_id).submission_key == unknown.submission_key
    assert all(turn.role != "ai_attendant" for turn in s.model.contexts[0].history)
    s.report(f"provider-{outcome}", automatic_resend=False)


def test_llm_timeout_uses_application_safe_handoff_without_claiming_model_reply(staging):
    s = staging
    s.inbound("Oi!")
    s.model.failure = GenerationTimeout("synthetic_llm_timeout")
    assert s.process() is not None
    delivery = s.deliver()
    assert delivery.body == "Vou pedir ajuda à equipe pra seguir com segurança."
    assert s.status(delivery).state is DeliveryState.DELIVERED
    s.report("llm-timeout", reply_source="application safe fallback; no inference")


def test_disconnect_reconnect_never_reactivates_channel_or_old_work(staging):
    s = staging
    s.inbound("Oi!")
    s.process()
    assert s.lifecycle("PARTNER_REMOVED").status_code == 204
    assert s.deliver() is None and not s.requests
    assert s.lifecycle("ACCOUNT_RECONNECTED").status_code == 204
    assert s.rows("channel_lifecycle")[0]["state"] == "verification_required"
    s.inbound("Depois da reconexão", identifier="reconnected")
    assert s.process() is None and s.deliver() is None
    assert s.rows("message_processing")[-1]["state"] == "suppressed"
    s.report("reconnect", active_inferred_from_reconnect=False)


def test_stale_restore_remains_quarantined_and_exposes_legacy_aud01_gap(staging):
    s = staging
    s.inbound("Oi!")
    s.process()
    snapshot = s.root / "before-submission.db"
    backup(s.path, snapshot)
    s.status(s.deliver())
    s.revoke()
    assert s.lifecycle("PARTNER_REMOVED").status_code == 204
    restored_path = s.root / "restored.db"
    backup(snapshot, restored_path)
    restored = create_telnyx_offline_app(
        s.settings, restored_path, wall_clock=lambda: s.now.timestamp()
    )
    assert restored.readiness()["egress"] is False
    claim = restored.store.claim_next_delivery(provider="telnyx", now=s.now + timedelta(seconds=2))
    request = s.signer.prepare(
        OutboundMessage(
            claim.provider_channel_id,
            claim.recipient_address,
            claim.body,
            submission_key=claim.submission_key,
        )
    )
    assert not restored.store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=request.message,
        http_request=request,
        now=s.now + timedelta(seconds=2),
    )
    # Explicitly reproduce the known generic legacy-store weakness, with NO sender.
    # Local snapshot looks active/consented and lost the original submission marker.
    legacy = SqliteConversationStore(restored_path, telnyx_request_signer=s.signer)
    assert legacy.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=request.message,
        http_request=request,
        now=s.now + timedelta(seconds=2),
    )
    assert len(s.requests) == 1  # no resubmission after either restore probe
    s.report("stale-restore", quarantined_denied=True, legacy_aud01_reproduced=True)


@pytest.mark.parametrize("gate", ["consent", "window", "quarantine", "request-integrity"])
def test_negative_authorization_gates_cannot_reach_fake_transport(staging, gate):
    s = staging
    s.inbound("Oi!")
    s.process()
    claim = s.store.claim_next_delivery(provider="telnyx", now=s.now + timedelta(seconds=1))
    request = s.signer.prepare(
        OutboundMessage(
            claim.provider_channel_id,
            claim.recipient_address,
            claim.body,
            submission_key=claim.submission_key,
        )
    )
    target = s.store
    if gate == "consent":
        with sqlite3.connect(s.path) as db:
            db.execute("DELETE FROM telnyx_consent")
    elif gate == "window":
        with sqlite3.connect(s.path) as db:
            db.execute(
                "UPDATE inbound_event_receipts SET message_occurred_at=?",
                ((s.now - timedelta(hours=24)).isoformat(),),
            )
    elif gate == "quarantine":
        target = s.app.store
    else:
        request = replace(request, content=b"{}")
    assert not target.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=request.message,
        http_request=request,
        now=s.now + timedelta(seconds=1),
    )
    assert not s.requests and s.rows("telnyx_http_requests") == []
    assert s.rows("outbound_deliveries")[0]["submission_started_at"] is None
    s.report(f"negative-{gate}", authorization_denied=True)


def test_bad_signature_has_no_effect_before_parsing(staging):
    s = staging
    assert s.post(wire(), corrupt=True).status_code == 403
    assert not s.rows("messages") and not s.rows("operational_events")
    assert not s.requests and not s.model.contexts
    s.report("negative-signature", auth_denied_before_persistence=True)


def test_ingress_only_has_no_background_workers_or_egress(staging):
    s = staging
    s.inbound("Oi!")
    assert s.app.readiness() == {
        "mode": "offline",
        "ingress": True,
        "persistence": True,
        "administration": False,
        "generation": False,
        "egress": False,
        "operational_channel": False,
        "quarantined": True,
    }
    assert not s.model.contexts and not s.requests and not s.rows("outbound_deliveries")
    s.report("ingress-only", background_workers=False)
