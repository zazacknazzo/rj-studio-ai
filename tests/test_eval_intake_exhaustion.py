from types import SimpleNamespace

from rj_studio_ai.evaluation.behavioral import score_appointment
from rj_studio_ai.handoff import HandoffReason


def state(count, *, service=None):
    return SimpleNamespace(
        state="collecting",
        clarification_count=count,
        recovery_offered=False,
        desired_service=service,
        preferred_day=None,
        preferred_time=None,
        professional_preference=None,
        request_kind="interest",
    )


def score(before, after, *, active=False, targets=(), service=None):
    return score_appointment(
        {"handoff": True, "handoff_on_intake_exhaustion": True},
        body="Vou chamar a equipe." if active else "Como posso ajudar?",
        intake=state(after, service=service),
        prior=state(before, service=service),
        active=active,
        authorized_targets=targets,
        handoff_reason=HandoffReason.APPOINTMENT_INTAKE_LIMIT if active else None,
    )


def test_four_turns_with_one_authorized_intake_question_do_not_exhaust_budget():
    for before, after, targets in [
        (0, 1, ("desired_service",)),
        (1, 1, ()),
        (1, 1, ()),
        (1, 1, ()),
    ]:
        assert all(score(before, after, targets=targets).values())


def test_budget_consumed_before_current_answer_requires_handoff():
    assert all(score(3, 3, active=True).values())
    assert not score(3, 3, active=False)["handoff_policy"]


def test_third_authorized_question_is_allowed_before_terminal_answer():
    assert all(score(2, 3, targets=("desired_service",)).values())


def test_above_budget_fails_even_if_handoff_occurred():
    assert not score(3, 4, active=True)["bounded_intake"]
    assert not score(4, 4, active=False)["handoff_policy"]


def test_runtime_cannot_keep_asking_when_budget_consumed():
    checks = score(3, 3, targets=("desired_service",))
    assert not checks["bounded_intake"]
    assert not checks["handoff_policy"]


def test_known_preference_question_still_fails():
    assert not score(1, 2, service="corte", targets=("desired_service",))["bounded_intake"]


def test_social_factual_and_general_turns_cannot_increment_intake_count():
    for _kind in ("social", "fact", "general_question"):
        assert all(score(1, 1).values())
        assert not score(1, 2)["bounded_intake"]


def test_multiple_authorized_targets_consume_one_question():
    assert all(score(1, 2, targets=("desired_service", "preferred_day")).values())
    assert not score(1, 3, targets=("desired_service", "preferred_day"))["bounded_intake"]


def test_premature_exhaustion_handoff_fails():
    assert not score(1, 1, active=True)["handoff_policy"]


def test_wrong_terminal_reason_still_fails():
    checks = score_appointment(
        {"handoff": True, "handoff_on_intake_exhaustion": True},
        body="Vou chamar a equipe.",
        intake=state(3),
        prior=state(3),
        active=True,
        authorized_targets=(),
        handoff_reason=HandoffReason.APPOINTMENT_INTEREST,
    )
    assert not checks["handoff_policy"]


class Model:
    def __init__(self, parts, intents=("appointment_interest",), refs=()):
        self.parts, self.intents, self.refs = parts, intents, refs

    def is_configured(self):
        return True

    def generate(self, message, *, context, remaining_budget):
        from rj_studio_ai.evaluation.suite import fixture_decision
        from rj_studio_ai.generation import GeneratedReply

        return GeneratedReply(
            decision=fixture_decision(
                surface="agentic",
                intents=self.intents,
                knowledge_refs=self.refs,
                reply_parts=self.parts,
            )
        )


def question():
    return {
        "kind": "conversation",
        "purpose": "question",
        "text": "Qual serviço você quer?",
        "targets": ["desired_service"],
    }


def send(store, model, body, identifier, context_builder=None):
    from rj_studio_ai.application import MessageResponder
    from rj_studio_ai.deadline import ExecutionDeadline
    from rj_studio_ai.evaluation.runner import synthetic_message
    from rj_studio_ai.persistence import DeliveryState

    reply = MessageResponder(
        store=store,
        generator=model,
        context_builder=context_builder,
        safe_failure_reply="Fallback",
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
    ).handle(synthetic_message(identifier, body), deadline=ExecutionDeadline.start())
    claim = store.get_generation(provider="eval", provider_message_id=identifier)
    return reply, store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)


def test_actual_runtime_exhausts_exactly_three_committed_questions(tmp_path):
    from rj_studio_ai.persistence import SqliteConversationStore

    store = SqliteConversationStore(tmp_path / "synthetic.db")
    store.initialize()
    for number, body in enumerate(["Quero marcar", "Não sei", "Ainda não sei"], 1):
        reply, intake = send(store, Model([question()]), body, str(number))
        assert intake.clarification_count == number
        assert not store.list_active_handoffs()
    reply, intake = send(store, Model([question()]), "Não tenho certeza", "4")
    assert intake.clarification_count == 3
    assert store.list_active_handoffs()[0].reason_code == HandoffReason.APPOINTMENT_INTAKE_LIMIT
    assert "?" not in reply.body


def test_social_fact_and_general_question_replies_do_not_consume_runtime_budget(tmp_path):
    import json
    from pathlib import Path

    from rj_studio_ai.conversation_context import (
        ConversationContextBuilder,
        ConversationContextLimits,
    )
    from rj_studio_ai.evaluation.runner import synthetic_facts
    from rj_studio_ai.evaluation.suite import load_suite
    from rj_studio_ai.persistence import SqliteConversationStore
    from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-multiple-facts"
    )
    facts = synthetic_facts(case)
    knowledge = tmp_path / "synthetic.yaml"
    knowledge.write_text(
        json.dumps({"version": 1, "facts": [f.model_dump(mode="json") for f in facts]})
    )
    repository = SalonKnowledgeRepository(knowledge)
    repository.load()
    store = SqliteConversationStore(tmp_path / "synthetic.db")
    store.initialize()
    builder = ConversationContextBuilder(
        store=store, salon_knowledge=repository, limits=ConversationContextLimits()
    )
    _, intake = send(store, Model([question()]), "Quero marcar", "1", builder)
    assert intake.clarification_count == 1
    _, intake = send(
        store,
        Model(
            [{"kind": "conversation", "purpose": "social", "text": "Por nada!"}], intents=["other"]
        ),
        "Obrigada",
        "2",
        builder,
    )
    assert intake.clarification_count == 1
    reply, intake = send(
        store,
        Model(
            [{"kind": "fact", "knowledge_ref": "hours-corte"}],
            intents=["hours"],
            refs=["hours-corte"],
        ),
        "Qual horário do corte?",
        "3",
        builder,
    )
    assert next(f.statement for f in facts if f.id == "hours-corte") in reply.body
    assert intake.clarification_count == 1
    reply, intake = send(
        store,
        Model(
            [
                {
                    "kind": "conversation",
                    "purpose": "question",
                    "text": "Qual resultado você gostaria de alcançar?",
                    "information_targets": ["customer_goal"],
                }
            ]
        ),
        "Ainda não sei",
        "4",
        builder,
    )
    assert "?" in reply.body
    assert intake.clarification_count == 1
    assert not store.list_active_handoffs()
