from datetime import date

import pytest

from rj_studio_ai.decision_policy import (
    DecisionPolicy,
    DecisionPolicyViolation,
)
from rj_studio_ai.llm_decision import (
    CriticalFactType,
    CriticalFactualClaim,
    Intent,
    LLMDecision,
    UncertaintyLevel,
)
from rj_studio_ai.salon_knowledge import (
    SalonKnowledgeCategory,
    SalonKnowledgeFact,
    SalonKnowledgeFactType,
    SalonKnowledgeStatus,
)


def _fact(
    *,
    identifier: str,
    category: SalonKnowledgeCategory,
    statement: str,
    topic: str = "progressiva",
    status: SalonKnowledgeStatus = SalonKnowledgeStatus.APPROVED,
    requires_human_consultation: bool = False,
    mandatory_policy_ids: tuple[str, ...] = (),
) -> SalonKnowledgeFact:
    return SalonKnowledgeFact(
        id=identifier,
        category=category,
        topic=topic,
        status=status,
        fact_type=SalonKnowledgeFactType.OPERATIONAL_COMMERCIAL,
        statement=statement,
        source="synthetic fixture",
        reviewed_at=date(2026, 9, 20),
        approved_by=("RJ Studio operator" if status is SalonKnowledgeStatus.APPROVED else None),
        requires_human_consultation=requires_human_consultation,
        mandatory_policy_ids=mandatory_policy_ids,
    )


def _decision(
    *,
    reply_text: str,
    claims: tuple[CriticalFactualClaim, ...] = (),
    intents: tuple[Intent, ...] = (Intent.PRICE,),
    knowledge_refs: tuple[str, ...] | None = None,
    handoff: bool = False,
) -> LLMDecision:
    return LLMDecision(
        intents=intents,
        reply_text=reply_text,
        uncertainty=UncertaintyLevel.LOW,
        knowledge_refs=(
            knowledge_refs
            if knowledge_refs is not None
            else tuple(claim.knowledge_ref for claim in claims)
        ),
        critical_claims=claims,
        handoff=handoff,
        handoff_reason=("O caso precisa da equipe." if handoff else None),
    )


def _claim(
    fact_type: CriticalFactType,
    value: str,
    knowledge_ref: str,
) -> CriticalFactualClaim:
    return CriticalFactualClaim(
        fact_type=fact_type,
        value=value,
        knowledge_ref=knowledge_ref,
    )


def test_accepts_a_canonical_grounded_claim() -> None:
    fact = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 180.",
    )
    decision = _decision(
        reply_text=fact.statement,
        claims=(_claim(CriticalFactType.PRICE, fact.statement, fact.id),),
    )

    result = DecisionPolicy().evaluate(decision, selected_knowledge=(fact,))

    assert result.reply_text == "A progressiva custa R$ 180."
    assert result.effective_handoff is False
    assert result.handoff_reason is None


def test_rejects_wrong_price_even_when_the_reference_and_claim_value_are_correct() -> None:
    fact = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 180.",
    )
    decision = _decision(
        reply_text="A progressiva custa R$ 150.",
        claims=(_claim(CriticalFactType.PRICE, fact.statement, fact.id),),
    )

    with pytest.raises(DecisionPolicyViolation, match="conflicts") as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=(fact,))

    assert captured.value.error_code == "grounding_rejection"


def test_rejects_one_valid_and_one_unstructured_invalid_fact() -> None:
    fact = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 180.",
    )
    decision = _decision(
        reply_text=f"{fact.statement}\n\nTambém abrimos às 7h.",
        claims=(_claim(CriticalFactType.PRICE, fact.statement, fact.id),),
    )

    with pytest.raises(DecisionPolicyViolation) as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=(fact,))

    assert captured.value.error_code == "grounding_rejection"


@pytest.mark.parametrize(
    ("category", "fact_type", "trusted", "proposed"),
    [
        (
            SalonKnowledgeCategory.PRICE,
            CriticalFactType.PRICE,
            "O preço exige avaliação da equipe.",
            "A progressiva fica R$ 200.",
        ),
        (
            SalonKnowledgeCategory.HOURS,
            CriticalFactType.HOURS,
            "O RJ Studio funciona das 9h às 18h.",
            "O RJ Studio funciona das 10h às 20h.",
        ),
        (
            SalonKnowledgeCategory.PROFESSIONAL,
            CriticalFactType.PROFESSIONAL,
            "Joelma realiza progressiva.",
            "Marina realiza progressiva.",
        ),
    ],
)
def test_rejects_a_claim_value_that_differs_from_trusted_knowledge(
    category: SalonKnowledgeCategory,
    fact_type: CriticalFactType,
    trusted: str,
    proposed: str,
) -> None:
    fact = _fact(identifier=f"known-{category.value}", category=category, statement=trusted)
    decision = _decision(
        reply_text=proposed,
        claims=(_claim(fact_type, proposed, fact.id),),
    )

    with pytest.raises(DecisionPolicyViolation, match="canonical") as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=(fact,))

    assert captured.value.error_code == "invalid_critical_claim"


def test_rejects_an_invented_price_when_trusted_knowledge_requires_evaluation() -> None:
    fact = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="O preço da progressiva exige avaliação da equipe.",
    )
    decision = _decision(reply_text="A progressiva fica R$ 200.", knowledge_refs=(fact.id,))

    with pytest.raises(DecisionPolicyViolation) as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=(fact,))

    assert captured.value.error_code == "grounding_rejection"


def test_rejects_fake_availability_without_a_trusted_integration() -> None:
    decision = _decision(
        reply_text="Temos horário disponível sexta às 15h.",
        intents=(Intent.APPOINTMENT_INTEREST,),
        knowledge_refs=(),
    )

    with pytest.raises(DecisionPolicyViolation) as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=())

    assert captured.value.error_code == "grounding_rejection"


@pytest.mark.parametrize(
    ("requires_human", "model_handoff", "expected"),
    [
        (False, False, False),
        (False, True, True),
        (True, False, True),
        (True, True, True),
    ],
)
def test_effective_handoff_is_mandatory_or_model_requested(
    requires_human: bool,
    model_handoff: bool,
    expected: bool,
) -> None:
    service = _fact(
        identifier="service-mega-hair",
        category=SalonKnowledgeCategory.SERVICE,
        statement="Mega hair exige avaliação da equipe.",
        topic="mega hair",
        requires_human_consultation=requires_human,
    )
    decision = _decision(
        reply_text="Posso ajudar com essa avaliação.",
        intents=(Intent.TECHNICAL_GUIDANCE,),
        knowledge_refs=(),
        handoff=model_handoff,
    )

    result = DecisionPolicy().evaluate(decision, selected_knowledge=(service,))

    assert result.effective_handoff is expected
    assert result.mandatory_handoff is requires_human
    if expected:
        assert result.handoff_reason is not None


def test_approved_handoff_condition_cannot_be_cancelled_by_the_model() -> None:
    condition = _fact(
        identifier="handoff-damage",
        category=SalonKnowledgeCategory.HANDOFF_CONDITION,
        statement="Relato de dano exige atendimento humano.",
        topic="dano",
    )
    decision = _decision(
        reply_text="Sinto muito pelo ocorrido.",
        intents=(Intent.COMPLAINT,),
        knowledge_refs=(),
        handoff=False,
    )

    result = DecisionPolicy().evaluate(decision, selected_knowledge=(condition,))

    assert result.effective_handoff
    assert result.mandatory_handoff
    assert result.handoff_reason == "approved_handoff_condition"


def test_trusted_active_handoff_cannot_be_cancelled_by_the_model() -> None:
    decision = _decision(
        reply_text="Recebi sua mensagem.",
        intents=(Intent.OTHER,),
        knowledge_refs=(),
        handoff=False,
    )

    result = DecisionPolicy().evaluate(
        decision,
        selected_knowledge=(),
        active_handoff=True,
    )

    assert result.effective_handoff
    assert result.mandatory_handoff
    assert result.handoff_reason == "active_handoff"


def test_rejects_missing_unapproved_mismatched_and_duplicate_claim_sources() -> None:
    approved_price = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 180.",
    )
    draft_price = _fact(
        identifier="price-draft",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 100.",
        status=SalonKnowledgeStatus.DRAFT,
    )
    cases = (
        (
            _decision(
                reply_text="A progressiva custa R$ 200.",
                claims=(_claim(CriticalFactType.PRICE, "A progressiva custa R$ 200.", "missing"),),
            ),
            (approved_price,),
        ),
        (
            _decision(
                reply_text=draft_price.statement,
                claims=(_claim(CriticalFactType.PRICE, draft_price.statement, draft_price.id),),
            ),
            (draft_price,),
        ),
        (
            _decision(
                reply_text=approved_price.statement,
                claims=(
                    _claim(
                        CriticalFactType.PROFESSIONAL, approved_price.statement, approved_price.id
                    ),
                ),
            ),
            (approved_price,),
        ),
        (
            _decision(
                reply_text=approved_price.statement,
                claims=(
                    _claim(CriticalFactType.PRICE, approved_price.statement, approved_price.id),
                    _claim(CriticalFactType.PRICE, approved_price.statement, approved_price.id),
                ),
                knowledge_refs=(approved_price.id,),
            ),
            (approved_price,),
        ),
    )

    for decision, knowledge in cases:
        with pytest.raises(DecisionPolicyViolation) as captured:
            DecisionPolicy().evaluate(decision, selected_knowledge=knowledge)
        assert captured.value.error_code == "invalid_critical_claim"


def test_accepts_multiple_canonical_claims_in_declared_order() -> None:
    price = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 180.",
    )
    hours = _fact(
        identifier="hours-studio",
        category=SalonKnowledgeCategory.HOURS,
        statement="O RJ Studio funciona das 9h às 18h.",
        topic="horário",
    )
    reply = f"{price.statement}\n\n{hours.statement}"
    decision = _decision(
        reply_text=reply,
        claims=(
            _claim(CriticalFactType.PRICE, price.statement, price.id),
            _claim(CriticalFactType.HOURS, hours.statement, hours.id),
        ),
        intents=(Intent.PRICE, Intent.HOURS),
    )

    result = DecisionPolicy().evaluate(decision, selected_knowledge=(price, hours))

    assert result.reply_text == reply


def test_service_claim_must_carry_every_selected_mandatory_policy() -> None:
    service = _fact(
        identifier="service-progressiva",
        category=SalonKnowledgeCategory.SERVICE,
        statement="A progressiva exige avaliação prévia.",
        mandatory_policy_ids=("policy-evaluation",),
    )
    policy = _fact(
        identifier="policy-evaluation",
        category=SalonKnowledgeCategory.POLICY,
        statement="A avaliação presencial é obrigatória antes do procedimento.",
        topic="avaliação",
    )
    decision = _decision(
        reply_text=service.statement,
        claims=(_claim(CriticalFactType.SERVICE, service.statement, service.id),),
        intents=(Intent.SERVICE_INFORMATION,),
    )

    with pytest.raises(DecisionPolicyViolation, match="mandatory policy") as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=(service, policy))

    assert captured.value.error_code == "invalid_critical_claim"


def test_service_claim_accepts_its_selected_mandatory_policy_in_the_same_reply() -> None:
    service = _fact(
        identifier="service-progressiva",
        category=SalonKnowledgeCategory.SERVICE,
        statement="A progressiva exige avaliação prévia.",
        mandatory_policy_ids=("policy-evaluation",),
    )
    policy = _fact(
        identifier="policy-evaluation",
        category=SalonKnowledgeCategory.POLICY,
        statement="A avaliação presencial é obrigatória antes do procedimento.",
        topic="avaliação",
    )
    reply = f"{service.statement}\n\n{policy.statement}"
    decision = _decision(
        reply_text=reply,
        claims=(
            _claim(CriticalFactType.SERVICE, service.statement, service.id),
            _claim(CriticalFactType.POLICY, policy.statement, policy.id),
        ),
        intents=(Intent.SERVICE_INFORMATION,),
    )

    result = DecisionPolicy().evaluate(decision, selected_knowledge=(service, policy))

    assert result.reply_text == reply


def test_customer_text_never_changes_the_selected_trusted_value() -> None:
    fact = _fact(
        identifier="price-progressiva",
        category=SalonKnowledgeCategory.PRICE,
        statement="A progressiva custa R$ 180.",
    )
    poisoned_proposal = _decision(
        reply_text="Como você disse, a progressiva custa R$ 100.",
        claims=(_claim(CriticalFactType.PRICE, "A progressiva custa R$ 100.", fact.id),),
    )

    with pytest.raises(DecisionPolicyViolation):
        DecisionPolicy().evaluate(poisoned_proposal, selected_knowledge=(fact,))


@pytest.mark.parametrize(
    "reply_text",
    [
        "A profissional Marina faz progressiva.",
        "Fazemos botox capilar.",
        "Nossa política permite qualquer atraso.",
        "Abrimos de manhã.",
    ],
)
def test_rejects_unstructured_critical_institutional_assertions(reply_text: str) -> None:
    decision = _decision(
        reply_text=reply_text,
        intents=(Intent.OTHER,),
        knowledge_refs=(),
    )

    with pytest.raises(DecisionPolicyViolation) as captured:
        DecisionPolicy().evaluate(decision, selected_knowledge=())

    assert captured.value.error_code == "grounding_rejection"


def test_allows_a_non_factual_clarification_without_knowledge() -> None:
    decision = _decision(
        reply_text="Posso confirmar essa informação com a equipe. Qual período você prefere?",
        intents=(Intent.PRICE, Intent.APPOINTMENT_INTEREST),
        knowledge_refs=(),
    )

    result = DecisionPolicy().evaluate(
        decision,
        selected_knowledge=(),
        customer_message="Quanto custa progressiva e tem horário sexta?",
    )

    assert result.reply_text == decision.reply_text


@pytest.mark.parametrize(
    "reply_text",
    [
        "A progressiva custa cento e cinquenta reais.",
        "A progressiva custa R＄ １５０.",
        "Marina é a profissional que faz esse serviço.",
    ],
)
def test_critical_customer_request_cannot_escape_by_omitting_structured_claims(
    reply_text: str,
) -> None:
    decision = _decision(
        reply_text=reply_text,
        intents=(Intent.OTHER,),
        knowledge_refs=(),
    )

    with pytest.raises(DecisionPolicyViolation) as captured:
        DecisionPolicy().evaluate(
            decision,
            selected_knowledge=(),
            customer_message="Quanto custa e qual profissional faz progressiva?",
        )

    assert captured.value.error_code == "grounding_rejection"
