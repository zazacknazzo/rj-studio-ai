import pytest

from rj_studio_ai.llm_decision import (
    CriticalFactType,
    Intent,
    StructuredDecisionValidationError,
    UncertaintyLevel,
    validate_llm_decision,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "intents": ["service_information"],
        "reply_text": "Temos informações aprovadas sobre esse serviço.",
        "uncertainty": "low",
        "knowledge_refs": ["service-corte"],
        "critical_claims": [
            {
                "fact_type": "service",
                "value": "Corte",
                "knowledge_ref": "service-corte",
            }
        ],
        "handoff": False,
        "handoff_reason": None,
    }
    payload.update(overrides)
    return payload


def test_valid_decision_is_a_named_domain_value_with_multiple_intents() -> None:
    decision = validate_llm_decision(
        _payload(intents=["price", "appointment_interest"]),
        allowed_knowledge_refs={"service-corte"},
    )

    assert decision.intents == (Intent.PRICE, Intent.APPOINTMENT_INTEREST)
    assert decision.uncertainty is UncertaintyLevel.LOW
    assert decision.critical_claims[0].fact_type is CriticalFactType.SERVICE
    assert decision.handoff is False
    assert decision.handoff_reason is None


@pytest.mark.parametrize("intent", [item.value for item in Intent])
def test_every_approved_intent_is_accepted(intent: str) -> None:
    decision = validate_llm_decision(
        _payload(intents=[intent], knowledge_refs=[], critical_claims=[]),
        allowed_knowledge_refs=set(),
    )

    assert decision.intents == (Intent(intent),)


def test_handoff_proposal_requires_a_reason() -> None:
    decision = validate_llm_decision(
        _payload(
            handoff=True,
            handoff_reason="O Customer pediu atendimento humano.",
            uncertainty="high",
        ),
        allowed_knowledge_refs={"service-corte"},
    )

    assert decision.handoff
    assert decision.handoff_reason == "O Customer pediu atendimento humano."


@pytest.mark.parametrize(
    "payload",
    [
        _payload(intents=["unknown"]),
        {"intents": ["greeting"]},
        _payload(intents=["price", "price"]),
        _payload(uncertainty="unknown"),
        _payload(handoff=True, handoff_reason=None),
        _payload(handoff=False, handoff_reason="motivo"),
        _payload(knowledge_refs=["missing-ref"]),
        _payload(critical_claims=[{"fact_type": "price", "value": "R$ 10"}]),
        _payload(reply_text=""),
        _payload(reply_text="x" * 801),
        _payload(unexpected="value"),
    ],
)
def test_invalid_or_untrusted_structured_values_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(StructuredDecisionValidationError):
        validate_llm_decision(payload, allowed_knowledge_refs={"service-corte"})


def test_claim_reference_must_be_declared_and_selected() -> None:
    with pytest.raises(StructuredDecisionValidationError):
        validate_llm_decision(
            _payload(
                knowledge_refs=[],
                critical_claims=[
                    {
                        "fact_type": "price",
                        "value": "R$ 10",
                        "knowledge_ref": "service-corte",
                    }
                ],
            ),
            allowed_knowledge_refs={"service-corte"},
        )
