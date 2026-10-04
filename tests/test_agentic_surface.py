from pathlib import Path

import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.evaluation.runner import synthetic_facts
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite
from rj_studio_ai.grounding import finalize_reply


def conversation(text, purpose="social", targets=()):
    return {"kind": "conversation", "purpose": purpose, "text": text, "targets": list(targets)}


def proposed(*parts, **kwargs):
    return fixture_decision(surface="agentic", reply_parts=list(parts), **kwargs)


@pytest.mark.parametrize("text", ["Oi, tudo bem?", "Olá! Que bom falar com você."])
def test_model_greeting_wording_is_retained_without_catalog_or_forced_cta(text):
    result = finalize_reply(
        proposed(conversation(text)), customer_message="Oi", context=ConversationContext((), ())
    )
    assert result.reply_text == text
    assert not result.handoff


@pytest.mark.parametrize(
    "text",
    [
        "Custa R$ 1,00.",
        "Você ganha desconto.",
        "Temos vaga amanhã.",
        "Seu horário está confirmado.",
        "Cancelei seu agendamento.",
        "Oferecemos cirurgia capilar.",
        "Seu profissional está confirmado.",
        "Nosso endereço é Rua Inventada.",
    ],
)
def test_free_protected_assertions_fail_safe(text):
    result = finalize_reply(
        proposed(conversation(text)), customer_message="Oi", context=ConversationContext((), ())
    )
    assert text not in result.reply_text
    assert result.handoff


def test_price_comes_from_fact_and_no_ack_or_cta_is_automatically_added():
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-divergent-price"
    )
    facts = synthetic_facts(case)
    result = finalize_reply(
        proposed(
            {"kind": "fact", "knowledge_ref": "price-corte"},
            intents=["price"],
            knowledge_refs=["price-corte"],
        ),
        customer_message="Quanto custa corte?",
        context=ConversationContext((), facts),
    )
    assert result.reply_text == "O corte custa R$ 120,00."
    assert not result.handoff


def test_false_model_human_intent_is_not_terminal_authority():
    result = finalize_reply(
        proposed(
            conversation("Oi!"),
            intents=["human_request"],
            handoff=True,
            handoff_reason="explicit_human_request",
        ),
        customer_message="Oi",
        context=ConversationContext((), ()),
    )
    assert not result.handoff
    assert result.reply_text == "Oi!"


@pytest.mark.parametrize(
    "body", ["Quero falar com uma pessoa.", "Meu couro cabeludo está ardendo."]
)
def test_trusted_safety_overrides_agentic_social_and_false_handoff(body):
    result = finalize_reply(
        proposed(conversation("Oi!"), handoff=False),
        customer_message=body,
        context=ConversationContext((), ()),
    )
    assert result.handoff


def test_invalid_reference_still_fails_closed():
    result = finalize_reply(
        proposed(
            {"kind": "fact", "knowledge_ref": "missing-fact"}, knowledge_refs=["missing-fact"]
        ),
        customer_message="Preço?",
        context=ConversationContext((), ()),
    )
    assert result.handoff and result.knowledge_refs == ()


def test_free_part_cannot_declare_action_capability():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        proposed({**conversation("Olá"), "authorized_action": "booking"})


def test_sanitized_trace_never_exports_conversational_prose_or_malformed_targets():
    from rj_studio_ai.evaluation.decision_trace import DecisionTraceCapture

    capture = DecisionTraceCapture()
    capture.propose(
        {
            "reply_parts": [
                {
                    "kind": "conversation",
                    "purpose": {"secret": "do-not-export"},
                    "targets": 42,
                    "text": "private output reasoning",
                },
                conversation("do-not-export", "question", ["preferred_day"]),
            ]
        },
        ConversationContext((), ()),
    )
    encoded = capture.trace.model_dump_json()
    assert "do-not-export" not in encoded and "reasoning" not in encoded
    assert capture.trace.proposed_appointment_targets == ("preferred_day",)


def test_two_facts_and_free_framing_preserve_values_and_qualifiers():
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-multiple-facts"
    )
    facts = synthetic_facts(case)
    result = finalize_reply(
        proposed(
            conversation("Veja só:", "transition"),
            *[{"kind": "fact", "knowledge_ref": f.id} for f in facts],
            intents=["price", "hours"],
            knowledge_refs=[f.id for f in facts],
        ),
        customer_message=case.data["customer_message"],
        context=ConversationContext((), facts),
    )
    assert not result.handoff
    assert all(f.statement in result.reply_text for f in facts)
    assert result.reply_text.startswith("Veja só:")


@pytest.mark.parametrize("text", ["Entendi!", "Posso te ajudar a escolher um dia?", "Obrigada!"])
def test_model_ack_cta_and_social_parts_do_not_require_one_string(text):
    result = finalize_reply(
        proposed(conversation(text)), customer_message="Oi", context=ConversationContext((), ())
    )
    assert result.reply_text == text
    assert not result.handoff


@pytest.mark.parametrize("fragments", [("Temos", "vaga amanhã."), ("Você ganha", "desconto.")])
def test_protected_assertions_cannot_bypass_guard_by_splitting_parts(fragments):
    result = finalize_reply(
        proposed(*(conversation(text) for text in fragments)),
        customer_message="Oi",
        context=ConversationContext((), ()),
    )
    assert result.handoff
