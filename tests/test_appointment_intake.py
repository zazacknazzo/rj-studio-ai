import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest
import yaml

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import GeneratedReply
from rj_studio_ai.llm_decision import LLMDecision
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)


class AppointmentModel:
    def is_configured(self):
        return True

    def __init__(self, **preferences):
        self.preferences = preferences
        self.calls = 0
        self.contexts = []
        self.intents = ["appointment_interest"]
        self.overrides = {}

    def generate(self, message, *, context, remaining_budget):
        self.calls += 1
        self.contexts.append(context)
        return GeneratedReply(
            decision=LLMDecision.model_validate(
                {
                    "intents": self.intents,
                    "reply_text": "Agendei: vaga confirmada às 14h com desconto de 90%.",
                    "reply_parts": [{"kind": "phrase", "phrase": "help"}],
                    "uncertainty": "low",
                    "knowledge_refs": [],
                    "critical_claims": [],
                    "handoff": False,
                    "handoff_reason": None,
                    "appointment_preferences": self.preferences,
                    **self.overrides,
                }
            )
        )


def message(
    identifier="interest-1", body="Quero progressiva sábado à tarde com Ana", customer="synthetic"
):
    return InboundMessage("meta", identifier, customer, "synthetic-channel", body)


def respond(store, model, inbound, *, preclaimed=None, context_builder=None):
    responder = MessageResponder(
        store=store,
        generator=model,
        safe_failure_reply="Fallback",
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
        context_builder=context_builder,
    )
    if preclaimed is not None:
        return responder.process_persisted(inbound, preclaimed=preclaimed)
    return responder.handle(inbound, deadline=ExecutionDeadline.start())


def test_complete_interest_opens_handoff_and_keeps_only_customer_preferences(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(
        desired_service="progressiva",
        preferred_time="sábado à tarde",
        professional_preference="Ana",
    )
    reply = respond(store, model, message())
    assert (
        reply.body == "Vou encaminhar essas informações para a equipe confirmar a disponibilidade."
    )
    handoff = store.list_active_handoffs()[0]
    intake = store.get_appointment_intake(conversation_id=handoff.conversation_id)
    assert intake.desired_service == "progressiva"
    assert intake.preferred_time == "sábado à tarde"
    assert intake.professional_preference == "Ana"
    assert intake.clarification_count == 0
    assert intake.state == "handoff"
    assert intake.handoff_token == handoff.owner_token


@pytest.mark.parametrize(
    "body,preferences,question",
    [
        (
            "Quero progressiva",
            {"desired_service": "progressiva"},
            "Qual dia ou período seria melhor para você?",
        ),
        (
            "Quero marcar sábado à tarde",
            {"preferred_time": "sábado à tarde"},
            "Qual serviço você gostaria de fazer?",
        ),
        ("Quero marcar", {}, "Qual serviço você gostaria de fazer?"),
    ],
)
def test_only_missing_required_detail_is_asked(tmp_path, body, preferences, question):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(**preferences)
    reply = respond(store, model, message(body=body))
    assert reply.body == question
    assert not store.list_active_handoffs()
    claim = store.get_generation(provider="meta", provider_message_id="interest-1")
    intake = store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)
    assert intake.clarification_count == 1


def test_short_replies_restart_and_retry_preserve_one_episode_and_two_question_limit(tmp_path):
    path = tmp_path / "intake.db"
    store = SqliteConversationStore(path)
    store.initialize()
    model = AppointmentModel()
    first = respond(store, model, message(body="Quero marcar"))
    first_claim = store.get_generation(provider="meta", provider_message_id="interest-1")
    initial = store.get_appointment_intake(inbound_message_id=first_claim.inbound_message_id)
    reopened = SqliteConversationStore(path)
    assert respond(reopened, model, message(body="Quero marcar")) == first
    assert model.calls == 1
    assert reopened.get_appointment_intake(conversation_id=initial.conversation_id) == initial

    model.preferences = {"desired_service": "progressiva"}
    model.intents = ["other"]
    second = respond(reopened, model, message("interest-2", "progressiva"))
    assert second.body == "Qual dia ou período seria melhor para você?"
    assert model.contexts[-1].appointment_intake.awaiting_field == "desired_service"
    midway = reopened.get_appointment_intake(conversation_id=initial.conversation_id)
    assert midway.episode_token == initial.episode_token
    assert midway.desired_service == "progressiva" and midway.clarification_count == 2
    model.preferences = {"preferred_time": "sábado à tarde"}
    final = respond(reopened, model, message("interest-3", "sábado à tarde"))
    assert "equipe confirmar a disponibilidade" in final.body
    handoff = reopened.list_active_handoffs()[0]
    result = reopened.get_appointment_intake(conversation_id=initial.conversation_id)
    assert result.preferred_time == "sábado à tarde" and result.clarification_count == 2
    assert result.handoff_token == handoff.owner_token


def test_two_unanswered_questions_end_in_handoff_even_when_incomplete(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel()
    for number, body in [(1, "Quero marcar"), (2, "Ainda não sei")]:
        reply = respond(store, model, message(f"interest-{number}", body))
        assert reply.body == "Qual serviço você gostaria de fazer?"
    reply = respond(store, model, message("interest-3", "Não sei"))
    assert "?" not in reply.body
    handoff = store.list_active_handoffs()[0]
    assert handoff.reason_code == "appointment_intake_limit"
    intake = store.get_appointment_intake(conversation_id=handoff.conversation_id)
    assert intake.desired_service is None and intake.preferred_time is None
    assert intake.clarification_count == 2


@pytest.mark.parametrize(
    "body",
    [
        "Quero alterar meu horário",
        "Quero cancelar meu agendamento",
        "Quero remarcar amanhã",
        "Quero reagendar",
        "Solicito cancelamento do horário",
    ],
)
def test_change_cancel_reschedule_go_direct_to_human_even_with_model_handoff_false(tmp_path, body):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    reply = respond(store, AppointmentModel(), message(body=body))
    handoff = store.list_active_handoffs()[0]
    assert "?" not in reply.body and "equipe" in reply.body
    assert store.get_appointment_intake(conversation_id=handoff.conversation_id) is None
    assert "confirmado" not in reply.body and "Agendei" not in reply.body


def test_model_cannot_invent_preferences_or_echo_booking_promises(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    reply = respond(
        store,
        AppointmentModel(desired_service="invented-service", preferred_time="14h"),
        message(body="Quero marcar"),
    )
    assert reply.body == "Qual serviço você gostaria de fazer?"
    claim = store.get_generation(provider="meta", provider_message_id="interest-1")
    intake = store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)
    assert intake.desired_service is None and intake.preferred_time is None


def test_release_ends_episode_without_reviving_suppressed_inbound_or_reusing_old_preferences(
    tmp_path,
):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde")
    respond(store, model, message())
    handoff = store.list_active_handoffs()[0]
    old = store.get_appointment_intake(conversation_id=handoff.conversation_id)
    assert respond(store, model, message("interest-2", "domingo")) is None
    calls = model.calls
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
    )
    assert store.get_appointment_intake(conversation_id=handoff.conversation_id).state == "released"
    assert respond(store, model, message("interest-2", "domingo")) is None
    assert model.calls == calls
    model.preferences = {}
    reply = respond(store, model, message("interest-3", "Quero marcar outra coisa"))
    assert reply.body == "Qual serviço você gostaria de fazer?"
    new = store.get_appointment_intake(conversation_id=handoff.conversation_id)
    assert new.episode_token != old.episode_token
    assert new.desired_service is None and new.preferred_time is None
    assert new.clarification_count == 1


def test_anthropic_receives_intake_as_untrusted_bounded_customer_context(tmp_path):
    from rj_studio_ai.providers.anthropic import AnthropicReplyGenerator

    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(desired_service="progressiva")
    respond(store, model, message(body="Quero progressiva"))
    model.preferences = {}
    respond(store, model, message("interest-2", "Ainda não sei"))
    context = model.contexts[-1]
    payload = AnthropicReplyGenerator._messages_for(message("interest-2", "Ainda não sei"), context)
    assert "progressiva" in payload[-1]["content"]
    assert "preferred_time" in payload[-1]["content"]
    assert payload[-1]["role"] == "user"
    instructions = AnthropicReplyGenerator._system_prompt_for(context)
    assert "appointment_preferences" in instructions
    assert "progressiva" not in instructions


def test_targeted_operator_inspection_exposes_only_three_preferences(tmp_path, monkeypatch, capsys):
    from rj_studio_ai import maintenance
    from rj_studio_ai.config import Settings

    path = tmp_path / "intake.db"
    store = SqliteConversationStore(path)
    store.initialize()
    respond(
        store,
        AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde"),
        message(),
    )
    handoff = store.list_active_handoffs()[0]
    monkeypatch.setattr(
        maintenance, "Settings", lambda: Settings(_env_file=None, database_path=path)
    )
    assert (
        maintenance.main(
            ["inspect-appointment-interest", "--conversation-id", str(handoff.conversation_id)]
        )
        == 0
    )
    result = capsys.readouterr().out
    assert "progressiva" in result and "sábado à tarde" in result
    assert "synthetic-channel" not in result and "Quero" not in result and "synthetic" not in result
    assert maintenance.main(["list-handoffs"]) == 0
    assert "progressiva" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "table",
    [
        "appointment_intakes",
        "messages",
        "outbound_deliveries",
        "message_processing",
        "conversation_handoffs",
    ],
)
def test_intake_reply_outbox_completion_and_handoff_rollback_together(tmp_path, table):
    path = tmp_path / "intake.db"
    store = SqliteConversationStore(path)
    store.initialize()
    inbound = message()
    claim = store.claim_generation(inbound)
    # Fault injection at a persistence boundary, not a mock of internals.
    event = "UPDATE OF state" if table == "message_processing" else "INSERT"
    condition = "WHEN NEW.direction = 'outbound'" if table == "messages" else ""
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"CREATE TRIGGER injected_failure BEFORE {event} ON {table} {condition} "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    with pytest.raises(PersistenceUnavailable):
        respond(
            store,
            AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde"),
            inbound,
            preclaimed=claim,
        )
    assert store.get_appointment_intake(inbound_message_id=claim.inbound_message_id) is None
    assert not store.list_active_handoffs()
    assert store.get_delivery_for_inbound(claim.inbound_message_id) is None
    state = store.get_generation(provider="meta", provider_message_id="interest-1")
    assert state.state is GenerationState.PROCESSING and state.reply_body is None
    assert len(store.get_history(provider="meta", customer_address="synthetic")) == 1


def test_concurrent_retries_commit_one_intake_and_one_handoff_confirmation(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    barrier = Barrier(2)
    model = AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde")

    def handle():
        barrier.wait()
        return respond(store, model, message())

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: handle(), range(2)))
    assert replies[0] == replies[1]
    assert model.calls == 1
    handoff = store.list_active_handoffs()[0]
    assert (
        store.get_appointment_intake(conversation_id=handoff.conversation_id).clarification_count
        == 0
    )
    assert len(store.get_history(provider="meta", customer_address="synthetic")) == 2


def test_expired_generation_cannot_overwrite_intake_of_current_owner(tmp_path):
    from rj_studio_ai.appointment_intake import plan_appointment_intake

    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    now = datetime.now(UTC)
    old = store.claim_generation(message(body="Quero marcar"), now=now)
    proposal = LLMDecision.model_validate(
        {
            "intents": ["appointment_interest"],
            "reply_text": "untrusted",
            "uncertainty": "low",
            "knowledge_refs": [],
            "critical_claims": [],
            "handoff": False,
            "handoff_reason": None,
        }
    )
    update = plan_appointment_intake(proposal, customer_message="Quero marcar", prior=None)
    current = store.claim_generation(message(body="Quero marcar"), now=now + timedelta(seconds=31))
    assert not store.complete_generation(
        inbound_message_id=old.inbound_message_id,
        owner_token=old.owner_token,
        reply_body="old",
        appointment_intake=update,
        now=now + timedelta(seconds=31),
    )
    assert store.get_appointment_intake(inbound_message_id=old.inbound_message_id) is None
    assert store.complete_generation(
        inbound_message_id=current.inbound_message_id,
        owner_token=current.owner_token,
        reply_body="Qual serviço?",
        appointment_intake=update,
        now=now + timedelta(seconds=32),
    )
    assert not store.complete_generation(
        inbound_message_id=old.inbound_message_id,
        owner_token=old.owner_token,
        reply_body="overwrite",
        appointment_intake=update,
        now=now + timedelta(seconds=33),
    )


@pytest.mark.parametrize(
    "overrides,body",
    [
        ({"knowledge_refs": ["unapproved-price"]}, "Quero progressiva sábado à tarde"),
        (
            {"intents": ["price", "appointment_interest"]},
            "Quanto custa? Quero progressiva sábado à tarde",
        ),
        ({}, "Meu couro cabeludo está ardendo. Quero progressiva sábado à tarde"),
        (
            {"intents": ["complaint", "appointment_interest"]},
            "Reclamação: Quero progressiva sábado à tarde",
        ),
        (
            {"intents": ["human_request", "appointment_interest"]},
            "Quero humano. Quero progressiva sábado à tarde",
        ),
        ({"handoff": True, "handoff_reason": "technical risk"}, "Quero progressiva sábado à tarde"),
    ],
)
def test_intake_cannot_bypass_grounding_or_other_handoff_rules(tmp_path, overrides, body):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde")
    model.overrides = overrides
    reply = respond(store, model, message(body=body))
    handoff = store.list_active_handoffs()[0]
    assert handoff.reason_code != "appointment_interest_collected"
    assert "?" not in reply.body and "Agendei" not in reply.body


def test_appointment_transparency_survives_collection_and_handoff(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(desired_service="progressiva")
    reply = respond(store, model, message(body="Você é uma IA? Quero progressiva"))
    assert "virtual" in reply.body and "dia ou período" in reply.body
    model.preferences = {"preferred_time": "sábado à tarde"}
    reply = respond(store, model, message("interest-2", "Você é robô? sábado à tarde"))
    assert "virtual" in reply.body and "equipe confirmar" in reply.body


def test_immediate_policy_handoff_does_not_count_an_unasked_question(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    model = AppointmentModel(desired_service="progressiva")
    model.overrides = {"handoff": True, "handoff_reason": "risk"}
    respond(store, model, message(body="Quero progressiva"))
    handoff = store.list_active_handoffs()[0]
    assert (
        store.get_appointment_intake(conversation_id=handoff.conversation_id).clarification_count
        == 0
    )


def test_later_inbound_cannot_generate_while_intake_handoff_is_completing(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db", busy_timeout_seconds=0.1)
    store.initialize()
    entered, continue_generation = Event(), Event()

    class SlowModel(AppointmentModel):
        def generate(self, *args, **kwargs):
            entered.set()
            assert continue_generation.wait(3)
            return super().generate(*args, **kwargs)

    model = SlowModel(desired_service="progressiva", preferred_time="sábado à tarde")
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(respond, store, model, message())
        try:
            assert entered.wait(3)
            # This short write must succeed while the LLM is outside SQLite.
            second = store.admit_generation(message("interest-2", "domingo"))
            assert second.state is GenerationState.RETRYABLE
            assert store.claim_generation(message("interest-2", "domingo")).blocked_by_predecessor
        finally:
            continue_generation.set()
        assert "equipe confirmar" in first.result().body
    assert respond(store, model, message("interest-2", "domingo")) is None
    assert model.calls == 1
    assert len(store.get_history(provider="meta", customer_address="synthetic")) == 3


def test_intakes_are_isolated_between_conversations(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    respond(
        store,
        AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde"),
        message(),
    )
    second = message("interest-b", "Quero marcar", "synthetic-b")
    reply = respond(store, AppointmentModel(), second)
    assert reply.body == "Qual serviço você gostaria de fazer?"
    assert len(store.list_active_handoffs()) == 1
    state = store.get_generation(provider="meta", provider_message_id="interest-b")
    assert (
        store.get_appointment_intake(inbound_message_id=state.inbound_message_id).desired_service
        is None
    )


def test_intake_uses_explicit_retention_purge_without_clearing_handoff(tmp_path):
    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    respond(
        store,
        AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde"),
        message(),
    )
    handoff = store.list_active_handoffs()[0]
    intake = store.get_appointment_intake(conversation_id=handoff.conversation_id)
    assert (
        SqliteConversationStore(tmp_path / "intake.db").get_appointment_intake(
            conversation_id=handoff.conversation_id
        )
        == intake
    )
    store.purge_messages_older_than(datetime.now(UTC) + timedelta(seconds=1))
    assert store.get_appointment_intake(conversation_id=handoff.conversation_id) is None
    assert store.list_active_handoffs() == [handoff]
    assert respond(store, AppointmentModel(), message("interest-new", "Quero marcar")) is None


def test_twilio_webhook_collects_short_turns_and_suppressed_retry_stays_suppressed_after_release(
    tmp_path,
):
    from fastapi.testclient import TestClient

    from rj_studio_ai.config import Settings
    from rj_studio_ai.main import create_app

    path = tmp_path / "twilio.db"
    model = AppointmentModel()
    app = create_app(
        Settings(
            _env_file=None,
            database_path=path,
            delivery_mode="legacy",
            whatsapp_provider="twilio",
            twilio_validate_signature=False,
        ),
        generator=model,
    )

    def post(client, identifier, body):
        return client.post(
            "/webhooks/twilio",
            data={
                "MessageSid": identifier,
                "From": "whatsapp:+5511000000000",
                "To": "whatsapp:+5511000000001",
                "Body": body,
            },
        )

    with TestClient(app) as client:
        first = post(client, "SM" + "1" * 32, "Quero marcar")
        assert first.status_code == 200 and "Qual serviço" in first.text
        model.preferences = {"desired_service": "progressiva"}
        model.intents = ["other"]
        second = post(client, "SM" + "2" * 32, "progressiva")
        assert second.status_code == 200 and "dia ou período" in second.text
        model.preferences = {"preferred_time": "sábado à tarde"}
        third = post(client, "SM" + "3" * 32, "sábado à tarde")
        assert third.status_code == 200 and "equipe confirmar" in third.text
        replay = post(client, "SM" + "3" * 32, "different body")
        # Legacy replay keeps the same persisted reply; proactive Meta below
        # acknowledges retries separately and has only one REST delivery.
        assert replay.status_code == 200 and replay.text == third.text
        blocked = post(client, "SM" + "4" * 32, "Continue")
        assert blocked.status_code == 200 and "<Message>" not in blocked.text
        store = SqliteConversationStore(path)
        handoff = store.list_active_handoffs()[0]
        assert store.release_handoff(
            conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
        )
        replay = post(client, "SM" + "4" * 32, "changed")
        assert "<Message>" not in replay.text and model.calls == 3
    assert store.get_appointment_intake(conversation_id=handoff.conversation_id).state == "released"


def test_meta_ack_processing_and_outbox_handoff_preserve_provider_lifecycle(tmp_path):
    import hashlib
    import hmac
    import json

    from fastapi.testclient import TestClient

    from rj_studio_ai.config import Settings
    from rj_studio_ai.delivery import OutboundDeliveryRunner
    from rj_studio_ai.main import create_app
    from rj_studio_ai.processing import ProcessingRunner
    from rj_studio_ai.providers.base import ProviderAcceptance
    from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

    class PausedExecutor:
        alive = False

        def start(self):
            self.alive = True

        def stop(self):
            self.alive = False

        def wake(self):
            pass

        def is_alive(self):
            return self.alive

    store = SqliteConversationStore(tmp_path / "meta.db")
    model = AppointmentModel(desired_service="progressiva", preferred_time="sábado à tarde")
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "meta.db",
            delivery_mode="proactive",
            whatsapp_provider="meta",
            meta_whatsapp_app_secret="synthetic-secret",
            meta_whatsapp_verify_token="synthetic-verify",
        ),
        store=store,
        generator=model,
        processing_executor=PausedExecutor(),
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "123456789012345"},
                            "messages": [
                                {
                                    "id": "wamid.synthetic",
                                    "from": "5511000000000",
                                    "type": "text",
                                    "text": {"body": "Quero progressiva sábado à tarde"},
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(b"synthetic-secret", body, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        ack = client.post(
            "/webhooks/meta",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
            },
        )
        assert ack.status_code == 200 and "equipe confirmar" not in ack.text
        assert model.calls == 0
    runner = ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=model,
            safe_failure_reply="Fallback",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    )
    completed = runner.run_once()
    handoff = store.list_active_handoffs()[0]
    delivery = store.get_delivery_for_inbound(completed.inbound_message_id)
    assert delivery.state is DeliveryState.PENDING and delivery.provider == "meta"
    assert delivery.handoff_token == handoff.owner_token
    sender = DeterministicFakeOutboundSender(
        outcomes=[ProviderAcceptance("wamid.synthetic-confirmation")]
    )
    outbound = OutboundDeliveryRunner(store=store, sender=sender, timeout_seconds=5)
    assert outbound.run_once() is not None
    assert outbound.run_once() is None and len(sender.calls) == 1
    assert store.get_delivery(delivery.delivery_id).state is DeliveryState.ACCEPTED
    assert (
        store.get_appointment_intake(conversation_id=handoff.conversation_id).preferred_time
        == "sábado à tarde"
    )


_APPOINTMENT_CASES = yaml.safe_load(
    (Path(__file__).parents[1] / "docs/evals/V1/appointment-interest-cases.yaml").read_text()
)["cases"]


@pytest.mark.parametrize("case", _APPOINTMENT_CASES, ids=lambda case: case["id"])
def test_synthetic_appointment_eval_policy_contract(tmp_path, case):
    store = SqliteConversationStore(tmp_path / "eval.db")
    store.initialize()
    model = AppointmentModel()
    for number, turn in enumerate(case["turns"], start=1):
        model.preferences = turn["preferences"]
        model.intents = turn.get("expected_intents", ["appointment_interest"])
        model.overrides = {
            "reply_text": turn.get("adversarial_reply_text", "Agendei. Sua vaga está reservada.")
        }
        reply = respond(store, model, message(f"eval-{number}", turn["customer_message"]))
        expected = turn["expected"]
        assert expected["contains"] in reply.body
        assert bool(store.list_active_handoffs()) is expected["handoff"]
        state = store.get_generation(provider="meta", provider_message_id=f"eval-{number}")
        intake = store.get_appointment_intake(inbound_message_id=state.inbound_message_id)
        if expected.get("intake_absent"):
            assert intake is None
        else:
            assert intake.clarification_count == expected["clarification_count"]
        for forbidden in (
            "Agendei",
            "vaga está reservada",
            "horário está confirmado",
            "Temos horário",
            "Está disponível",
            "Pode vir",
            "vaga está confirmada",
        ):
            assert forbidden not in reply.body


def test_intake_frame_consumes_context_budget_and_never_reuses_released_preferences(tmp_path):
    from rj_studio_ai.conversation_context import (
        ConversationContextBuilder,
        ConversationContextLimits,
        ConversationContextTooLarge,
    )
    from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

    path = tmp_path / "intake.db"
    store = SqliteConversationStore(path)
    store.initialize()
    respond(
        store, AppointmentModel(desired_service="progressiva"), message(body="Quero progressiva")
    )
    current = store.admit_generation(message("interest-2", "sábado"))
    source = tmp_path / "empty.yaml"
    source.write_text("version: 1\nfacts: []\n")
    knowledge = SalonKnowledgeRepository(source)
    knowledge.load()
    builder = ConversationContextBuilder(
        store=store,
        salon_knowledge=knowledge,
        limits=ConversationContextLimits(
            total_input_token_budget=100, prompt_overhead_token_budget=0
        ),
    )
    with pytest.raises(ConversationContextTooLarge):
        builder.build(inbound_message_id=current.inbound_message_id, current_body="sábado")


def test_stale_episode_snapshot_cannot_partially_finalize_current_generation(tmp_path):
    from dataclasses import replace

    from rj_studio_ai.appointment_intake import plan_appointment_intake
    from rj_studio_ai.handoff import HandoffReason

    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    respond(
        store, AppointmentModel(desired_service="progressiva"), message(body="Quero progressiva")
    )
    second_message = message("interest-2", "sábado")
    claim = store.claim_generation(second_message)
    prior = store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)
    decision = (
        AppointmentModel(preferred_time="sábado")
        .generate(second_message, context=None, remaining_budget=5)
        .decision
    )
    update = plan_appointment_intake(decision, customer_message="sábado", prior=prior)
    assert not store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="confirmation",
        appointment_intake=replace(update, expected_episode_token="stale-token"),
        handoff_reason=HandoffReason.APPOINTMENT_INTEREST,
    )
    assert store.get_appointment_intake(conversation_id=prior.conversation_id) == prior
    assert store.get_delivery_for_inbound(claim.inbound_message_id) is None
    assert not store.list_active_handoffs()
    assert store.complete_generation(
        inbound_message_id=claim.inbound_message_id,
        owner_token=claim.owner_token,
        reply_body="confirmation",
        appointment_intake=update,
        handoff_reason=HandoffReason.APPOINTMENT_INTEREST,
    )


def test_incomplete_intake_keeps_approved_location_answer_for_multi_intent(tmp_path):
    from rj_studio_ai.conversation_context import (
        ConversationContextBuilder,
        ConversationContextLimits,
    )
    from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

    store = SqliteConversationStore(tmp_path / "intake.db")
    store.initialize()
    source = tmp_path / "synthetic.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "facts": [
                    {
                        "id": "location-synthetic",
                        "category": "location",
                        "topic": "endereço",
                        "status": "approved",
                        "fact_type": "operational_commercial",
                        "statement": "O endereço sintético é Rua Exemplo, 100.",
                        "source": "synthetic fixture",
                        "reviewed_at": "2026-10-02",
                        "approved_by": "synthetic-operator",
                    }
                ],
            }
        )
    )
    knowledge = SalonKnowledgeRepository(source)
    knowledge.load()
    builder = ConversationContextBuilder(
        store=store, salon_knowledge=knowledge, limits=ConversationContextLimits()
    )
    model = AppointmentModel(desired_service="progressiva")
    model.intents = ["location", "appointment_interest"]
    model.overrides = {
        "knowledge_refs": ["location-synthetic"],
        "reply_parts": [{"kind": "fact", "knowledge_ref": "location-synthetic"}],
    }
    reply = respond(
        store, model, message(body="Quero progressiva. Qual é o endereço?"), context_builder=builder
    )
    assert (
        reply.body
        == "O endereço sintético é Rua Exemplo, 100. Qual dia ou período seria melhor para você?"
    )
    assert not store.list_active_handoffs()
