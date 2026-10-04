"""Compose customer-visible facts from approved data, never from model prose."""

from rj_studio_ai.appointment_intake import AppointmentIntakeUpdate
from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.handoff import HandoffReason, apply_handoff_policy
from rj_studio_ai.livia_persona import (
    HUMAN_REVIEW_REPLY,
    REPLY_PHRASES,
    LiviaPersona,
    PersonaValidationError,
)
from rj_studio_ai.llm_decision import (
    CriticalFactType,
    CriticalFactualClaim,
    FactReplyPart,
    Intent,
    LLMDecision,
    PhraseReplyPart,
    ReplyPhrase,
    StructuredDecisionValidationError,
    UncertaintyLevel,
    validate_llm_decision,
)
from rj_studio_ai.salon_knowledge import SalonKnowledgeCategory, SalonKnowledgeStatus


def finalize_reply(
    decision: LLMDecision,
    *,
    customer_message: str,
    context: ConversationContext,
    appointment_intake: AppointmentIntakeUpdate | None = None,
) -> LLMDecision:
    """Return a trusted rendering while retaining the structured decision seam."""
    facts = {
        fact.id: fact for fact in context.knowledge if fact.status is SalonKnowledgeStatus.APPROVED
    }
    required_reason = LiviaPersona().required_handoff_reason(customer_message)
    if required_reason is not None:
        return _clarify(decision, customer_message, required_reason)
    try:
        validate_llm_decision(decision.model_dump(mode="json"), allowed_knowledge_refs=set(facts))
    except StructuredDecisionValidationError:
        return _clarify(decision, customer_message, "unavailable_knowledge")

    for fact in facts.values():
        if fact.requires_human_consultation:
            return _clarify(decision, customer_message, "requires_human_consultation")
        if fact.category is SalonKnowledgeCategory.HANDOFF_CONDITION:
            return _clarify(decision, customer_message, "approved_handoff_condition")
        if any(policy_id not in facts for policy_id in fact.mandatory_policy_ids):
            return _clarify(decision, customer_message, "unavailable_mandatory_policy")
    if set(decision.intents) & {
        Intent.HUMAN_REQUEST,
        Intent.COMPLAINT,
    } or (Intent.APPOINTMENT_CHANGE in decision.intents and appointment_intake is None):
        return _clarify(decision, customer_message, "human_review_required")
    decision = apply_handoff_policy(decision)
    for claim in decision.critical_claims:
        if facts[claim.knowledge_ref].category.value != claim.fact_type.value:
            return _clarify(decision, customer_message, "unsupported_critical_claim")
    if not decision.reply_parts:
        return _clarify(decision, customer_message, "missing_reply_plan")
    rendered_categories = {
        facts[part.knowledge_ref].category
        for part in decision.reply_parts
        if isinstance(part, FactReplyPart)
    }
    if not rendered_categories and any(
        isinstance(part, PhraseReplyPart) and part.phrase is ReplyPhrase.INFORMATION
        for part in decision.reply_parts
    ):
        return _clarify(decision, customer_message, "missing_critical_fact")
    required_categories = {
        Intent.PRICE: SalonKnowledgeCategory.PRICE,
        Intent.HOURS: SalonKnowledgeCategory.HOURS,
        Intent.PROFESSIONAL: SalonKnowledgeCategory.PROFESSIONAL,
        Intent.SERVICE_INFORMATION: SalonKnowledgeCategory.SERVICE,
        Intent.LOCATION: SalonKnowledgeCategory.LOCATION,
        Intent.PROMOTION_OR_DISCOUNT: SalonKnowledgeCategory.POLICY,
    }
    clarification = _commercial_clarification(decision, context, rendered_categories)
    if clarification is not None:
        if LiviaPersona().requires_identity_transparency(customer_message):
            clarification = REPLY_PHRASES[ReplyPhrase.IDENTITY] + " " + clarification
        return decision.model_copy(
            update={
                "reply_text": clarification,
                "uncertainty": UncertaintyLevel.HIGH,
            }
        )
    if any(
        intent in required_categories and required_categories[intent] not in rendered_categories
        for intent in decision.intents
    ):
        return _clarify(decision, customer_message, "missing_critical_fact")

    persona = LiviaPersona()
    prior_replies = tuple(turn.body for turn in context.history if turn.role == "ai_attendant")
    rendered: list[str] = []
    claims: list[CriticalFactualClaim] = []
    references: list[str] = []
    parts = list(decision.reply_parts)
    for fact in facts.values():
        # Mandatory policies apply to selected Services, even if the model omits
        # the Service and its policy references from its proposal.
        for policy_id in fact.mandatory_policy_ids:
            if not any(
                isinstance(part, FactReplyPart) and part.knowledge_ref == policy_id
                for part in parts
            ):
                parts.append(FactReplyPart(kind="fact", knowledge_ref=policy_id))
    for part in parts:
        if isinstance(part, PhraseReplyPart):
            # The bounded intake owns its single question. Keep approved facts
            # and acknowledgements, but never append a second catalog question.
            if appointment_intake is not None and "?" in REPLY_PHRASES[part.phrase]:
                continue
            rendered.append(
                persona.phrase(
                    part.phrase, customer_message=customer_message, prior_ai_replies=prior_replies
                )
            )
        elif isinstance(part, FactReplyPart):
            fact = facts[part.knowledge_ref]
            if fact.id in references:
                continue
            references.append(fact.id)
            if len(fact.statement) > 800:
                return _clarify(decision, customer_message, "unsafe_reply_surface")
            rendered.append(fact.statement)
            if fact.category.value in CriticalFactType:
                claims.append(
                    CriticalFactualClaim(
                        fact_type=CriticalFactType(fact.category.value),
                        value=fact.statement,
                        knowledge_ref=fact.id,
                    )
                )
    if persona.requires_identity_transparency(customer_message):
        rendered.insert(0, REPLY_PHRASES[ReplyPhrase.IDENTITY])
    text = persona.compose_reply(
        rendered,
        customer_message=customer_message,
        prior_ai_replies=prior_replies,
        commercial_answer=appointment_intake is None
        and bool(rendered_categories)
        and not set(decision.intents)
        & {
            Intent.APPOINTMENT_INTEREST,
            Intent.APPOINTMENT_CHANGE,
            Intent.TECHNICAL_GUIDANCE,
            Intent.COMPLAINT,
        },
    )
    try:
        persona.validate_reply(
            customer_message,
            text,
            prior_ai_replies=tuple(
                turn.body for turn in context.history if turn.role == "ai_attendant"
            ),
        )
    except PersonaValidationError:
        return _clarify(decision, customer_message, "unsafe_reply_surface")
    return decision.model_copy(
        update={
            "reply_text": text,
            "critical_claims": tuple(claims),
            "knowledge_refs": tuple(dict.fromkeys((*decision.knowledge_refs, *references))),
            "uncertainty": decision.uncertainty if rendered else UncertaintyLevel.HIGH,
        }
    )


def _clarify(decision: LLMDecision, customer_message: str, reason: str) -> LLMDecision:
    text = REPLY_PHRASES[ReplyPhrase.CLARIFICATION]
    if reason in {
        "requires_human_consultation",
        "approved_handoff_condition",
        "human_review_required",
        "explicit_human_request",
        "personalized_technical_risk",
        "alleged_damage",
        "payment_problem",
        "legal_threat",
        "relevant_complaint",
    }:
        text = HUMAN_REVIEW_REPLY
    if LiviaPersona().requires_identity_transparency(customer_message):
        text = REPLY_PHRASES[ReplyPhrase.IDENTITY] + " " + text
    authorized = apply_handoff_policy(decision, required_reason=HandoffReason(reason))
    return authorized.model_copy(
        update={
            "reply_text": text,
            "reply_parts": (),
            "knowledge_refs": (),
            "critical_claims": (),
            "uncertainty": UncertaintyLevel.HIGH,
        }
    )


def _commercial_clarification(
    decision: LLMDecision,
    context: ConversationContext,
    rendered_categories: set[SalonKnowledgeCategory],
) -> str | None:
    """One controlled question, never an exception for an attempted factual answer."""
    if any(fact.mandatory_policy_ids for fact in context.knowledge):
        return None
    if rendered_categories or decision.critical_claims or decision.knowledge_refs:
        return None
    if len(decision.reply_parts) != 1 or not isinstance(decision.reply_parts[0], PhraseReplyPart):
        return None
    phrase = decision.reply_parts[0].phrase
    choices = {
        ReplyPhrase.PRICE_SERVICE_QUESTION: (Intent.PRICE, SalonKnowledgeCategory.PRICE),
        ReplyPhrase.DISCOUNT_SERVICE_QUESTION: (
            Intent.PROMOTION_OR_DISCOUNT,
            SalonKnowledgeCategory.POLICY,
        ),
    }
    if phrase not in choices:
        return None
    intent, category = choices[phrase]
    if intent not in decision.intents or set(decision.intents) - {
        intent,
        Intent.GREETING,
        Intent.OTHER,
    }:
        return None
    if any(fact.category is category for fact in context.knowledge):
        return None
    questions = {REPLY_PHRASES[key] for key in choices}
    previous = next((t.body for t in reversed(context.history) if t.role == "ai_attendant"), "")
    if any(question in previous for question in questions):
        return None
    return REPLY_PHRASES[phrase]
