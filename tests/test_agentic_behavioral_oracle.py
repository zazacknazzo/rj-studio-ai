from pathlib import Path
from types import SimpleNamespace

import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.evaluation.oracle import GroundingObservation, replay_grounding
from rj_studio_ai.evaluation.runner import synthetic_facts
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


@pytest.mark.parametrize(
    "question",
    ["Qual dia seria melhor pra você?", "Tem algum dia que fica melhor pra você?"],
)
def test_policy_and_missing_preference_question_are_behavioral_not_catalog(question):
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-mandatory-policy"
    )
    context = ConversationContext((), synthetic_facts(case))
    decision = fixture_decision(
        intents=["promotion_or_discount"],
        knowledge_refs=["policy-corte"],
        reply_parts=[{"kind": "fact", "knowledge_ref": "policy-corte"}],
    )
    body = "Não há desconto autorizado para corte. " + question
    observed = GroundingObservation.capture(
        case, decision=decision, context=context, body=body, handoff_active=False
    )
    assert replay_grounding(case, observed, body=body)["trusted_facts"] == "pass"


@pytest.mark.parametrize("extra", ["O corte custa R$ 1,00.", "Sua vaga está confirmada."])
def test_behavioral_oracle_does_not_allow_untrusted_assertions_around_approved_policy(extra):
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-mandatory-policy"
    )
    context = ConversationContext((), synthetic_facts(case))
    decision = fixture_decision(**case.data["proposal"])
    body = "Não há desconto autorizado para corte. " + extra
    observed = GroundingObservation.capture(
        case, decision=decision, context=context, body=body, handoff_active=False
    )
    assert replay_grounding(case, observed, body=body)["trusted_facts"] == "fail"


@pytest.mark.parametrize(
    "wording", ["Qual dia você prefere para fazer o corte?", "Que dia prefere fazer o corte?"]
)
def test_question_about_day_can_mention_already_known_service(wording):
    from rj_studio_ai.conversational_surface import question_fields

    assert question_fields(wording) == {"preferred_day"}


def test_active_handoff_does_not_certify_false_price_or_booking():
    from rj_studio_ai.evaluation.behavioral import score_appointment

    expected = {"handoff": True}
    intake = SimpleNamespace(clarification_count=0)
    checks = score_appointment(
        expected,
        body="Sua vaga está confirmada. Custa R$ 1,00.",
        intake=intake,
        prior=None,
        active=True,
        trusted_confirmation="Vou chamar alguém da equipe.",
    )
    assert checks["no_booking_claim"] is False


def test_no_question_cannot_increase_counter():
    from rj_studio_ai.evaluation.behavioral import score_appointment

    checks = score_appointment(
        {"handoff": False},
        body="Como posso ajudar.",
        intake=SimpleNamespace(clarification_count=3),
        prior=None,
        active=False,
    )
    assert checks["bounded_intake"] is False


def test_counter_uses_authorized_target_not_lexical_wording():
    from rj_studio_ai.evaluation.behavioral import score_appointment

    state = SimpleNamespace(
        clarification_count=1,
        desired_service="corte",
        preferred_day="sexta",
        preferred_time=None,
        professional_preference=None,
        recovery_offered=False,
    )
    checks = score_appointment(
        {"handoff": False},
        body="Você prefere cedo ou mais para o fim do expediente?",
        intake=state,
        prior=None,
        active=False,
        authorized_targets=("preferred_time",),
        expected_preferences={"desired_service": "corte", "preferred_day": "sexta"},
    )
    assert checks["bounded_intake"]


def test_persisted_invented_preference_does_not_pass_behavioral_state_check():
    from rj_studio_ai.evaluation.behavioral import score_appointment

    checks = score_appointment(
        {"handoff": False},
        body="Qual dia funciona melhor?",
        intake=SimpleNamespace(
            clarification_count=1,
            desired_service="inventado",
            preferred_day=None,
            preferred_time=None,
            professional_preference=None,
            recovery_offered=False,
        ),
        prior=None,
        active=False,
        authorized_targets=("preferred_day",),
        expected_preferences={"desired_service": "corte"},
    )
    assert not checks["bounded_intake"]


def test_grounding_question_can_mention_known_day_when_collecting_time():

    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-mandatory-policy"
    )
    state = SimpleNamespace(
        desired_service="corte",
        preferred_day="sexta",
        preferred_time=None,
        professional_preference=None,
    )
    context = ConversationContext((), synthetic_facts(case), appointment_intake=state)
    decision = fixture_decision(
        surface="agentic",
        intents=["promotion_or_discount"],
        knowledge_refs=["policy-corte"],
        reply_parts=[
            {"kind": "fact", "knowledge_ref": "policy-corte"},
            {
                "kind": "conversation",
                "purpose": "question",
                "text": "Qual horário no dia escolhido fica melhor para você?",
                "targets": ["preferred_time"],
            },
        ],
    )
    body = (
        "Não há desconto autorizado para corte. "
        "Qual horário no dia escolhido fica melhor para você?"
    )
    observed = GroundingObservation.capture(
        case,
        decision=decision,
        context=context,
        body=body,
        handoff_active=False,
        authorized_question_targets=("preferred_time",),
    )
    assert replay_grounding(case, observed, body=body)["trusted_facts"] == "pass"


def test_persisted_intake_integrity_is_a_critical_contract():
    cases = load_suite(Path("docs/evals/V1")).cases
    assert all(
        c.contract.checks["bounded_intake"].critical for c in cases if c.kind == "appointment"
    )
