from pathlib import Path

import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.evaluation.runner import synthetic_facts
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite
from rj_studio_ai.grounding import finalize_reply


def part(text, *, purpose="clarification", information_targets=("service",)):
    return {
        "kind": "conversation",
        "purpose": purpose,
        "text": text,
        "targets": [],
        "information_targets": list(information_targets),
    }


def proposal(*parts, intents=("price",), **kwargs):
    return fixture_decision(surface="agentic", intents=intents, reply_parts=list(parts), **kwargs)


def price_context():
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-divergent-price"
    )
    return ConversationContext((), synthetic_facts(case))


def test_general_service_gap_renders_model_question_without_intake():
    text = "De qual serviço você quer conhecer o valor?"
    result = finalize_reply(
        proposal(part(text)), customer_message="Qual preço?", context=ConversationContext((), ())
    )
    assert result.reply_text == text
    assert not result.handoff and result.knowledge_refs == ()


@pytest.mark.parametrize(
    "text",
    [
        "Qual serviço você está buscando?",
        "Me conta qual serviço você tem em mente?",
    ],
)
def test_general_clarification_preserves_free_wording(text):
    result = finalize_reply(
        proposal(part(text)), customer_message="Qual preço?", context=ConversationContext((), ())
    )
    assert result.reply_text == text and not result.handoff


def test_discount_request_can_clarify_without_granting_discount():
    text = "Para qual serviço você gostaria de saber mais?"
    result = finalize_reply(
        proposal(part(text), intents=["promotion_or_discount"]),
        customer_message="Consegue desconto?",
        context=ConversationContext((), ()),
    )
    assert result.reply_text == text and not result.handoff


@pytest.mark.parametrize("continuation", ["", "Que resultado você tem em mente?"])
def test_trusted_price_with_optional_continuation_has_no_forced_cta(continuation):
    pieces = [{"kind": "fact", "knowledge_ref": "price-corte"}]
    if continuation:
        pieces.append(part(continuation, purpose="question", information_targets=["customer_goal"]))
    result = finalize_reply(
        proposal(*pieces, knowledge_refs=["price-corte"]),
        customer_message="Quanto custa o corte?",
        context=price_context(),
    )
    assert result.reply_text == "O corte custa R$ 120,00." + (
        " " + continuation if continuation else ""
    )
    assert not result.handoff


def test_general_service_question_is_denied_when_customer_service_is_known():
    result = finalize_reply(
        proposal(
            {"kind": "fact", "knowledge_ref": "price-corte"},
            part("Qual serviço você deseja?"),
            knowledge_refs=["price-corte"],
            appointment_preferences={"desired_service": "corte"},
        ),
        customer_message="Quanto custa o corte?",
        context=price_context(),
    )
    assert result.reply_text == "O corte custa R$ 120,00."


def test_selected_candidate_does_not_make_service_known():
    text = "De qual serviço você quer saber o valor?"
    result = finalize_reply(
        proposal(part(text)), customer_message="Qual preço?", context=price_context()
    )
    assert result.reply_text == text and not result.handoff


@pytest.mark.parametrize(
    "information_targets", [("service",), ("customer_goal",), ("clarification",)]
)
def test_general_question_creates_no_intake_or_counter(tmp_path, information_targets):
    from test_agentic_intake import Model, send

    from rj_studio_ai.persistence import SqliteConversationStore

    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    text = "Me conta um pouco mais do que procura?"
    reply, intake = send(
        store,
        Model([part(text, information_targets=information_targets)], intents=["price"]),
        "Qual preço?",
    )
    assert reply.body == text and intake is None
    assert not store.list_active_handoffs()


@pytest.mark.parametrize(
    "targets,text",
    [
        (["service"], "Qual serviço você quer?"),
        (["customer_goal"], "Qual dia você prefere?"),
        (["clarification"], "Qual período você prefere?"),
    ],
)
def test_general_label_cannot_bypass_intake_known_fields_or_counter(tmp_path, targets, text):
    from test_agentic_intake import Model, send

    from rj_studio_ai.persistence import SqliteConversationStore

    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    reply, intake = send(
        store,
        Model([part(text, information_targets=targets)], preferences={"desired_service": "corte"}),
        "Quero corte",
    )
    assert text not in reply.body and intake.clarification_count == 0
    assert not store.list_active_handoffs()


@pytest.mark.parametrize(
    "text",
    [
        "O desconto é de 50%.",
        "Temos vaga amanhã.",
        "Agendei seu corte.",
        "O serviço custa USD 1.",
        "Funcionamos das 9 às 18.",
    ],
)
def test_general_question_label_cannot_authorize_facts_or_actions(text):
    result = finalize_reply(
        proposal(part(text)), customer_message="Qual preço?", context=ConversationContext((), ())
    )
    assert text not in result.reply_text and result.handoff


@pytest.mark.parametrize("purpose", ["cta", "social", "recovery"])
def test_general_scope_is_only_for_information_questions(purpose):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        proposal(part("Qual serviço?", purpose=purpose))


def test_general_scope_cannot_be_combined_with_appointment_effect_target():
    from pydantic import ValidationError

    mixed = {**part("Qual serviço?"), "targets": ["desired_service"]}
    with pytest.raises(ValidationError):
        proposal(mixed)


@pytest.mark.parametrize(
    "action",
    [
        "answer_only",
        "clarify",
        "continue_conversation",
        "social_response",
        "request_human_attention",
    ],
)
def test_next_action_is_advisory_and_has_no_handoff_or_wording_effect(action):
    result = finalize_reply(
        proposal(
            part("Me conta um pouco mais?", information_targets=["customer_goal"]),
            next_action=action,
        ),
        customer_message="Qual preço?",
        context=ConversationContext((), ()),
    )
    assert result.reply_text == "Me conta um pouco mais?" and not result.handoff
    assert result.next_action == action


def test_shared_prompt_teaches_steering_and_information_scope_without_catalog():
    from rj_studio_ai.livia_persona import agentic_surface_instructions

    instructions = agentic_surface_instructions()
    assert "information_targets" in instructions
    assert "customer_goal" in instructions
    assert "next_action" in instructions
    assert "entender" in instructions and "próximo passo" in instructions
    assert "não é obrigatório" in instructions
    assert "Quanto custa o corte?" not in instructions
    assert "Qual preço?" not in instructions


def captured_trace(decision, customer="Qual preço?", context=None):
    from rj_studio_ai import application
    from rj_studio_ai.evaluation.decision_trace import DecisionTraceCapture, capture_finalizer

    context = context or ConversationContext((), ())
    capture = DecisionTraceCapture()
    capture.propose(decision.model_dump(mode="json"), context)
    with capture_finalizer(capture):
        final = application.finalize_reply(decision, customer_message=customer, context=context)
    return capture.finish(final.reply_text, safe_fallback=False), final


def test_trace_records_retained_general_question_and_advisory_plan_without_prose():
    trace, final = captured_trace(
        proposal(part("De qual serviço você quer saber mais?"), next_action="clarify")
    )
    assert trace.proposed_information_targets == ("service",)
    assert trace.retained_information_targets == ("service",)
    assert trace.actionable_information_targets == ("service",)
    assert trace.proposed_next_action == "clarify"
    assert trace.authorized_appointment_targets == ()
    assert not trace.commercial_continuation_present
    assert final.reply_text not in trace.model_dump_json()


@pytest.mark.parametrize(
    "text", ["Posso ajudar com outra dúvida?", "Como posso ajudar?", "Entendi."]
)
def test_generic_fallback_with_misleading_label_is_not_an_actionable_clarification(text):
    trace, _ = captured_trace(proposal(part(text)))
    assert trace.actionable_information_targets == ()


def test_trace_continuation_is_observed_only_when_part_really_rendered():
    trace, _ = captured_trace(
        proposal(
            {"kind": "fact", "knowledge_ref": "price-corte"},
            part(
                "Quer me contar o que procura?",
                purpose="commercial_continuation",
                information_targets=[],
            ),
            knowledge_refs=["price-corte"],
            next_action="continue_conversation",
        ),
        customer="Quanto custa o corte?",
        context=price_context(),
    )
    assert trace.commercial_continuation_present
    plain, _ = captured_trace(
        proposal(
            {"kind": "fact", "knowledge_ref": "price-corte"},
            knowledge_refs=["price-corte"],
            next_action="continue_conversation",
        ),
        customer="Quanto custa o corte?",
        context=price_context(),
    )
    assert not plain.commercial_continuation_present


def test_behavioral_eval_fails_generic_fallback_but_keeps_factual_safety_separate():
    from rj_studio_ai.evaluation.oracle import GroundingObservation, replay_grounding

    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-unknown-price"
    )
    decision = proposal(part("Posso ajudar com outra dúvida?"))
    trace, final = captured_trace(decision)
    observed = GroundingObservation.capture(
        case,
        decision=decision,
        context=ConversationContext((), ()),
        body=final.reply_text,
        handoff_active=False,
        actionable_information_targets=trace.actionable_information_targets,
    )
    checks = replay_grounding(case, observed, body=final.reply_text)
    assert checks["trusted_facts"] == "pass"
    assert checks["general_clarification"] == "fail"


def test_general_target_and_next_action_trace_are_allowlisted():
    from rj_studio_ai.evaluation.decision_trace import DecisionTraceCapture

    capture = DecisionTraceCapture()
    capture.propose(
        {
            "next_action": "private-secret-value",
            "reply_parts": [
                {
                    "kind": "conversation",
                    "information_targets": ["service", "private-customer-message"],
                    "text": "private prose",
                    "reasoning": "private reasoning",
                }
            ],
        },
        ConversationContext((), ()),
    )
    assert capture.trace.proposed_next_action is None
    assert capture.trace.proposed_information_targets == ("service",)
    assert "private" not in capture.trace.model_dump_json()


@pytest.mark.parametrize(
    "phrase",
    [
        "De qual atendimento gostaria de saber o valor?",
        "O que você quer fazer?",
        "Qual é seu objetivo?",
    ],
)
def test_actionable_clarification_checks_meaning_not_exact_sentence(phrase):
    target = "customer_goal" if "objetivo" in phrase else "service"
    trace, _ = captured_trace(proposal(part(phrase, information_targets=[target])))
    assert trace.actionable_information_targets == (target,)


def test_service_already_known_in_persisted_intake_is_not_asked_again(tmp_path):
    from test_agentic_intake import Model, send
    from test_agentic_intake import part as intake_part

    from rj_studio_ai.persistence import SqliteConversationStore

    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    _, before = send(
        store,
        Model(
            [intake_part("Qual dia?", ["preferred_day"])], preferences={"desired_service": "corte"}
        ),
        "Quero corte",
    )
    reply, after = send(
        store, Model([part("Qual serviço você deseja?")], intents=["price"]), "Qual preço?", "two"
    )
    assert "Qual serviço" not in reply.body
    assert after.desired_service == "corte"
    assert after.clarification_count == before.clarification_count == 1


def test_general_goal_question_during_intake_does_not_charge_preference_budget(tmp_path):
    from test_agentic_intake import Model, send

    from rj_studio_ai.persistence import SqliteConversationStore

    store = SqliteConversationStore(tmp_path / "case.db")
    store.initialize()
    wording = "Qual resultado você está buscando?"
    reply, state = send(
        store,
        Model(
            [part(wording, information_targets=["customer_goal"])],
            preferences={"desired_service": "corte"},
        ),
        "Quero corte",
    )
    assert reply.body == wording and state.clarification_count == 0


def test_provider_neutral_schema_requires_explicit_scopes_and_advisory_plan():
    from rj_studio_ai.llm_decision import decision_json_schema

    schema = decision_json_schema()
    part_schema = schema["$defs"]["ConversationalReplyPart"]
    assert set(part_schema["required"]) == set(part_schema["properties"])
    assert "default" not in part_schema["properties"]["information_targets"]
    assert "next_action" in schema["required"]
    assert "default" not in schema["properties"]["next_action"]


def test_historical_v3_replay_does_not_add_new_commercial_expectations():
    from rj_studio_ai.evaluation.oracle import (
        PHASE_ONE_ORACLE_VERSION,
        GroundingObservation,
        _oracle_digest,
        replay_grounding,
    )

    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-unknown-price"
    )
    body = "Posso ajudar com outra dúvida?"
    observed = GroundingObservation.capture(
        case,
        decision=proposal(part(body)),
        context=ConversationContext((), ()),
        body=body,
        handoff_active=False,
    )
    historic = observed.model_copy(
        update={
            "oracle_version": PHASE_ONE_ORACLE_VERSION,
            "oracle": _oracle_digest(case, PHASE_ONE_ORACLE_VERSION),
        }
    )
    assert "general_clarification" not in replay_grounding(case, historic, body=body)
    assert replay_grounding(case, historic, body=body)["trusted_facts"] == "pass"


def test_historical_v8_record_remains_loadable(tmp_path):
    import json

    from rj_studio_ai.evaluation.live import LiveRecord

    historical = Path("work/evals/openai-agentic-surface-smoke-2026-10-04-01/phase-A.json")
    if not historical.exists():
        pytest.skip("Local history evidence is not checked into Git")
    record = LiveRecord.model_validate(json.loads(historical.read_text()))
    assert record.schema_version == 8


def test_general_question_purpose_can_resolve_missing_service_without_handoff():
    wording = "Qual serviço você está pensando em fazer?"
    result = finalize_reply(
        proposal(part(wording, purpose="question")),
        customer_message="Qual preço?",
        context=ConversationContext((), ()),
    )
    assert result.reply_text == wording and not result.handoff


@pytest.mark.parametrize(
    "wording",
    [
        "Posso ajudar com outra dúvida sobre o serviço?",
        "Quer saber mais sobre o serviço?",
        "Posso ajudar com outra dúvida sobre o resultado?",
    ],
)
def test_topic_mention_alone_does_not_resolve_information_gap(wording):
    target = "customer_goal" if "resultado" in wording else "service"
    trace, _ = captured_trace(proposal(part(wording, information_targets=[target])))
    assert trace.actionable_information_targets == ()


def test_released_intake_service_does_not_block_new_general_question_after_restart(tmp_path):
    from test_agentic_intake import Model, send
    from test_agentic_intake import part as intake_part

    from rj_studio_ai.persistence import SqliteConversationStore

    path = tmp_path / "case.db"
    store = SqliteConversationStore(path)
    store.initialize()
    send(
        store,
        Model(
            [intake_part("Entendi.", purpose="acknowledgement")],
            preferences={
                "desired_service": "corte",
                "preferred_day": "sexta",
                "preferred_time": "à tarde",
            },
        ),
        "Quero corte sexta à tarde",
    )
    handoff = store.list_active_handoffs()[0]
    store.release_handoff(conversation_id=handoff.conversation_id, owner_token=handoff.owner_token)
    reopened = SqliteConversationStore(path)
    wording = "De qual serviço você quer saber o valor?"
    reply, state = send(reopened, Model([part(wording)], intents=["price"]), "Qual preço?", "two")
    assert reply.body == wording
    assert state.state == "released" and state.desired_service == "corte"
    assert not reopened.list_active_handoffs()
