import pytest

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.suite import fixture_decision
from rj_studio_ai.generation import GeneratedReply
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore


class Model:
    def __init__(self, parts, preferences=None, intents=("appointment_interest",)):
        self.parts, self.preferences, self.intents = parts, preferences, intents

    def is_configured(self):
        return True

    def generate(self, message, *, context, remaining_budget):
        return GeneratedReply(
            decision=fixture_decision(
                surface="agentic",
                intents=self.intents,
                reply_parts=self.parts,
                appointment_preferences=self.preferences,
            )
        )


def part(text, targets=(), purpose="question"):
    return {"kind": "conversation", "purpose": purpose, "text": text, "targets": list(targets)}


def send(store, model, body, identifier="one"):
    reply = MessageResponder(
        store=store,
        generator=model,
        safe_failure_reply="Fallback",
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
    ).handle(
        InboundMessage("meta", identifier, "synthetic", "synthetic", body),
        deadline=ExecutionDeadline.start(),
    )
    claim = store.get_generation(provider="meta", provider_message_id=identifier)
    return reply, store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)


def test_model_selects_time_before_day_and_wording_is_retained(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, intake = send(
        store,
        Model(
            [part("Você prefere manhã ou tarde?", ["preferred_time"])], {"desired_service": "corte"}
        ),
        "Quero corte",
    )
    assert reply.body == "Você prefere manhã ou tarde?"
    assert intake.awaiting_field == "preferred_time"
    assert intake.clarification_count == 1


def test_social_turn_preserves_preferences_without_spending_question_budget(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, intake = send(
        store,
        Model([part("Que bom!", purpose="social")], {"desired_service": "corte"}),
        "Quero corte",
    )
    assert reply.body == "Que bom!"
    assert intake.desired_service == "corte"
    assert intake.clarification_count == 0
    assert intake.awaiting_field is None


def test_combined_missing_targets_cost_one_question_not_two(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    _, intake = send(
        store,
        Model(
            [part("Qual dia e período ficam melhores?", ["preferred_day", "preferred_time"])],
            {"desired_service": "corte"},
        ),
        "Quero corte",
    )
    assert intake.clarification_count == 1
    assert intake.awaiting_field == "preferred_day"


def test_known_field_question_is_denied_without_charging_budget(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, intake = send(
        store,
        Model([part("Qual serviço você quer?", ["desired_service"])], {"desired_service": "corte"}),
        "Quero corte",
    )
    assert "Qual serviço" not in reply.body
    assert intake.desired_service == "corte" and intake.clarification_count == 0
    assert not store.list_active_handoffs()


def test_model_can_ack_during_intake_without_forced_next_question(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    _, before = send(
        store,
        Model([part("Algum dia em mente?", ["preferred_day"])], {"desired_service": "corte"}),
        "Quero corte",
    )
    reply, after = send(
        store, Model([part("Por nada!", purpose="social")], intents=["other"]), "Obrigada", "two"
    )
    assert reply.body == "Por nada!"
    assert after.clarification_count == before.clarification_count == 1
    assert after.desired_service == "corte"


def test_cancellation_wording_varies_but_offer_is_durable_and_unique(tmp_path):
    path = tmp_path / "case.db"
    store = SqliteConversationStore(path)
    store.initialize()
    offer = "Entendi. Você gostaria de tentar outro dia antes de cancelar?"
    reply, before = send(
        store,
        Model([part(offer, ["cancellation_choice"], "recovery")], intents=["appointment_change"]),
        "Quero cancelar meu agendamento",
    )
    assert reply.body == offer
    assert before.recovery_offered and before.clarification_count == 1
    reopened = SqliteConversationStore(path)
    # Retry replays exactly, without offering a second time.
    replay, same = send(reopened, Model([], intents=["other"]), "Quero cancelar meu agendamento")
    assert replay == reply and same == before
    final, after = send(
        reopened,
        Model([part(offer, ["cancellation_choice"], "recovery")], intents=["appointment_change"]),
        "Quero cancelar mesmo",
        "two",
    )
    assert final.body != offer
    assert after.recovery_offered and after.clarification_count == 1
    assert after.state == "handoff" and reopened.list_active_handoffs()


def test_complete_preferences_require_handoff_without_real_booking(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, state = send(
        store,
        Model(
            [part("Entendi!", purpose="acknowledgement")],
            {"desired_service": "corte", "preferred_day": "sexta", "preferred_time": "à tarde"},
        ),
        "Quero corte sexta à tarde",
    )
    assert state.state == "handoff" and state.clarification_count == 0
    assert store.list_active_handoffs()
    assert "confirmar" in reply.body and "agendei" not in reply.body.casefold()


def test_unsafe_model_action_never_becomes_trusted_state(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, state = send(
        store,
        Model(
            [part("Agendei. Sua vaga está confirmada.", ["preferred_time"])],
            {"desired_service": "corte"},
        ),
        "Quero corte",
    )
    assert "Agendei" not in reply.body
    assert state.clarification_count == 0
    assert store.list_active_handoffs()


def test_model_can_delay_recovery_without_losing_the_single_opportunity(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, before = send(
        store,
        Model([part("Entendi.", purpose="acknowledgement")], intents=["appointment_change"]),
        "Quero cancelar meu agendamento",
    )
    assert reply.body == "Entendi."
    assert not before.recovery_offered and before.clarification_count == 0
    reply, after = send(
        store,
        Model(
            [part("Você gostaria de tentar outro dia?", ["cancellation_choice"], "recovery")],
            intents=["other"],
        ),
        "Estou pensando",
        "two",
    )
    assert after.recovery_offered and after.clarification_count == 1
    assert not store.list_active_handoffs()


def test_ordinary_question_during_intake_does_not_require_preference_target(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    wording = "Quer que eu explique como funciona?"
    reply, state = send(store, Model([part(wording)], {"desired_service": "corte"}), "Quero corte")
    assert reply.body == wording
    assert state.clarification_count == 0
    assert not store.list_active_handoffs()


def test_numeric_time_preference_question_does_not_assert_hours_or_availability(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    wording = "Você prefere antes ou depois das 15h?"
    reply, state = send(
        store,
        Model([part(wording, ["preferred_time"])], {"desired_service": "corte"}),
        "Quero corte",
    )
    assert reply.body == wording
    assert state.clarification_count == 1
    assert not store.list_active_handoffs()


def test_generic_trusted_appointment_change_still_requires_durable_handoff(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, state = send(
        store,
        Model([part("Entendi!", purpose="social")], intents=["other"]),
        "Quero alterar meu horário",
    )
    assert state is None
    assert store.list_active_handoffs()
    assert reply.body != "Entendi!"


def test_unlabelled_preference_question_cannot_escape_counter_using_cta_purpose(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    wording = "Qual dia seria melhor?"
    reply, state = send(
        store, Model([part(wording, purpose="cta")], {"desired_service": "corte"}), "Quero corte"
    )
    assert wording not in reply.body
    assert state.clarification_count == 0
    assert not store.list_active_handoffs()


def test_retained_time_question_charges_only_its_actual_authorized_target(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    wording = "O que acha de fazer à tarde?"
    reply, state = send(
        store,
        Model([part(wording, ["preferred_time"])], {"desired_service": "corte"}),
        "Quero corte",
    )
    assert reply.body == wording
    assert state.clarification_count == 1 and state.awaiting_field == "preferred_time"


def test_vetoed_part_cannot_persist_phantom_question_or_recovery(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    _, state = send(
        store,
        Model(
            [part("Temos vaga às 15h?", ["cancellation_choice"], "recovery")],
            intents=["appointment_change"],
        ),
        "Quero cancelar meu agendamento",
    )
    assert state.clarification_count == 0
    assert state.awaiting_field is None
    assert not state.recovery_offered
    assert state.state == "handoff"


@pytest.mark.parametrize(
    "wording,purpose",
    [
        ("Como foi seu dia?", "social"),
        ("Posso te ajudar a escolher um dia?", "cta"),
        ("Como foi sua manhã?", "social"),
        ("Posso te ajudar a escolher um horário?", "cta"),
        ("Quer que eu explique o trabalho do profissional?", "question"),
    ],
)
def test_social_day_mentions_and_offers_are_not_preference_collection(tmp_path, wording, purpose):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, state = send(
        store, Model([part(wording, purpose=purpose)], {"desired_service": "corte"}), "Quero corte"
    )
    assert reply.body == wording
    assert state.clarification_count == 0
    assert not store.list_active_handoffs()


def test_colon_clock_preference_question_is_equivalent_to_h_clock(tmp_path):
    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    wording = "Você prefere antes ou depois das 15:00?"
    reply, state = send(
        store,
        Model([part(wording, ["preferred_time"])], {"desired_service": "corte"}),
        "Quero corte",
    )
    assert reply.body == wording
    assert state.clarification_count == 1
    assert not store.list_active_handoffs()
