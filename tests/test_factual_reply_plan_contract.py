import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.openai_live import OpenAIEvalGenerator
from rj_studio_ai.evaluation.suite import fixture_decision
from rj_studio_ai.grounding import finalize_reply
from rj_studio_ai.livia_persona import reply_plan_instructions
from rj_studio_ai.llm_decision import (
    StructuredDecisionValidationError,
    decision_json_schema,
    validate_llm_decision,
)
from rj_studio_ai.providers.anthropic import AnthropicReplyGenerator, LLMPriceTable
from rj_studio_ai.salon_knowledge import SalonKnowledgeFact


def fact(identifier, category, statement):
    return SalonKnowledgeFact.model_validate(
        {
            "id": identifier,
            "category": category,
            "topic": "synthetic",
            "status": "approved",
            "fact_type": "operational_commercial",
            "statement": statement,
            "source": "synthetic fixture",
            "reviewed_at": date(2026, 10, 2),
            "approved_by": "synthetic-operator",
        }
    )


FACTS = (
    fact("price-synthetic", "price", "Preço sintético: R$ 75,00."),
    fact("hours-synthetic", "hours", "Horário sintético: 10h às 16h."),
    fact("professional-synthetic", "professional", "Profissional sintética: Exemplo."),
)


def adapter_request(tmp_path, provider, context, decision):
    requests = []
    message = InboundMessage("eval", "one", "synthetic", "synthetic", "Dúvida sintética")
    if provider == "anthropic":

        class Messages:
            def create(self, **kwargs):
                requests.append(kwargs)
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=decision.model_dump_json())],
                    model="claude-sonnet-5",
                    usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
                )

        adapter = AnthropicReplyGenerator(
            api_key="synthetic-value",
            model="claude-sonnet-5",
            max_output_tokens=200,
            pricing=LLMPriceTable(
                input_microusd_per_million=3_000_000,
                output_microusd_per_million=15_000_000,
            ),
            client=SimpleNamespace(messages=Messages()),
        )
        result = adapter.generate(message, context=context, remaining_budget=9)
        return (
            result.decision,
            requests[0]["system"],
            requests[0]["output_config"]["format"]["schema"],
        )

    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "service_tier": "default",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": decision.model_dump_json()}],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "total_tokens": 1100,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        ledger = BudgetLedger(tmp_path / "budget.jsonl", LivePricing.load())
        try:
            adapter = OpenAIEvalGenerator(
                api_key="synthetic-value", client=client, ledger=ledger, phase="A"
            )
            result = adapter.generate(message, context=context, remaining_budget=9)
        finally:
            ledger.close()
    return result.decision, requests[0]["instructions"], requests[0]["text"]["format"]["schema"]


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_both_adapters_instruct_every_supported_factual_intent_once(tmp_path, provider):
    context = ConversationContext((), FACTS[:2])
    decision = fixture_decision(
        intents=["price", "hours"],
        knowledge_refs=["price-synthetic", "hours-synthetic"],
        reply_parts=[
            {"kind": "fact", "knowledge_ref": "price-synthetic"},
            {"kind": "fact", "knowledge_ref": "hours-synthetic"},
        ],
    )
    generated, instructions, schema = adapter_request(tmp_path, provider, context, decision)
    assert "Para cada intent factual reconhecido" in instructions
    assert "todos os intents factuais" in instructions
    assert "Intents não factuais" in instructions
    assert instructions.count(reply_plan_instructions()) == 1
    assert schema == decision_json_schema()
    assert generated == decision
    result = finalize_reply(generated, customer_message="Dúvida sintética", context=context)
    assert result.handoff is False
    assert result.knowledge_refs == ("price-synthetic", "hours-synthetic")
    assert all(f.statement in result.reply_text for f in context.knowledge)


def planned_decision(intents, references):
    return fixture_decision(
        intents=intents,
        knowledge_refs=references,
        reply_parts=[{"kind": "fact", "knowledge_ref": ref} for ref in references],
    )


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
@pytest.mark.parametrize(
    ("intents", "references"),
    [
        (["price"], ["price-synthetic"]),
        (["greeting", "price"], ["price-synthetic"]),
        (
            ["price", "hours", "professional"],
            ["price-synthetic", "hours-synthetic", "professional-synthetic"],
        ),
    ],
    ids=["single-fact", "factual-and-nonfactual", "three-factual-intents"],
)
def test_adapters_preserve_general_factual_plans_without_inventing_extra_refs(
    tmp_path, provider, intents, references
):
    context = ConversationContext((), tuple(f for f in FACTS if f.id in references))
    decision = planned_decision(intents, references)
    generated, instructions, schema = adapter_request(tmp_path, provider, context, decision)
    assert generated == decision
    assert schema == decision_json_schema()
    assert instructions.count(reply_plan_instructions()) == 1
    assert all(f.id not in reply_plan_instructions() for f in FACTS)
    result = finalize_reply(generated, customer_message="Dúvida sintética", context=context)
    assert result.handoff is False
    assert result.knowledge_refs == tuple(references)
    assert {p.knowledge_ref for p in result.reply_parts} == set(references)


@pytest.mark.parametrize("count", [2, 3])
def test_each_factual_intent_still_requires_its_ref_and_fact_part(count):
    references = [f.id for f in FACTS[:count]]
    context = ConversationContext((), FACTS[:count])
    decision = planned_decision(["price", "hours", "professional"][:count], references)
    for reference in references:
        missing_ref = decision.model_dump(mode="json")
        missing_ref["knowledge_refs"].remove(reference)
        with pytest.raises(StructuredDecisionValidationError):
            validate_llm_decision(missing_ref, allowed_knowledge_refs=set(references))
        missing_part = decision.model_copy(
            update={
                "reply_parts": tuple(
                    p for p in decision.reply_parts if p.knowledge_ref != reference
                )
            }
        )
        result = finalize_reply(missing_part, customer_message="Dúvida sintética", context=context)
        assert result.handoff is True
        assert result.handoff_reason == "missing_critical_fact"
        assert result.knowledge_refs == ()


def test_unavailable_factual_intent_still_hands_off_without_fabricating_refs():
    decision = planned_decision(["price", "hours"], ["price-synthetic"])
    result = finalize_reply(
        decision, customer_message="Dúvida sintética", context=ConversationContext((), FACTS[:1])
    )
    assert decision.knowledge_refs == ("price-synthetic",)
    assert result.handoff is True
    assert result.handoff_reason == "missing_critical_fact"
    assert result.knowledge_refs == ()
    assert result.reply_parts == ()


@pytest.mark.parametrize("model_requested", [False, True])
def test_factual_plan_never_prevents_legitimate_explicit_handoff(model_requested):
    decision = planned_decision(["price", "hours"], ["price-synthetic", "hours-synthetic"])
    if model_requested:
        decision = decision.model_copy(
            update={"handoff": True, "handoff_reason": "human_review_required"}
        )
    result = finalize_reply(
        decision,
        customer_message="Dúvida sintética" if model_requested else "Quero falar com uma pessoa",
        context=ConversationContext((), FACTS[:2]),
    )
    assert result.handoff is True
    assert result.handoff_reason == (
        "human_review_required" if model_requested else "explicit_human_request"
    )
    assert result.reply_parts == ()


def test_invalid_factual_reference_still_fails_safely():
    decision = planned_decision(["price"], ["invented-synthetic"])
    with pytest.raises(StructuredDecisionValidationError):
        validate_llm_decision(
            decision.model_dump(mode="json"), allowed_knowledge_refs={"price-synthetic"}
        )
    result = finalize_reply(
        decision, customer_message="Dúvida sintética", context=ConversationContext((), FACTS[:1])
    )
    assert result.handoff is True
    assert result.handoff_reason == "unavailable_knowledge"
    assert result.knowledge_refs == ()
