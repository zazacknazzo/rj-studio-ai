"""Localized human-review reasons and truthful confirmation text."""

from enum import StrEnum

from rj_studio_ai.livia_persona import REPLY_PHRASES, LiviaPersona
from rj_studio_ai.llm_decision import ReplyPhrase


class HandoffReason(StrEnum):
    EXPLICIT_HUMAN_REQUEST = "explicit_human_request"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    TECHNICAL_RISK = "personalized_technical_risk"
    ALLEGED_DAMAGE = "alleged_damage"
    PAYMENT_PROBLEM = "payment_problem"
    LEGAL_THREAT = "legal_threat"
    COMPLAINT = "relevant_complaint"
    CONSULTATION = "requires_human_consultation"
    APPROVED_CONDITION = "approved_handoff_condition"
    UNAVAILABLE_KNOWLEDGE = "unavailable_knowledge"
    UNAVAILABLE_POLICY = "unavailable_mandatory_policy"
    UNSUPPORTED_CLAIM = "unsupported_critical_claim"
    MISSING_PLAN = "missing_reply_plan"
    MISSING_FACT = "missing_critical_fact"
    UNSAFE_SURFACE = "unsafe_reply_surface"
    MODEL_REQUEST = "model_requested_handoff"
    GENERATION_UNAVAILABLE = "generation_unavailable"
    APPOINTMENT_INTEREST = "appointment_interest_collected"
    APPOINTMENT_INTAKE_LIMIT = "appointment_intake_limit"
    APPOINTMENT_CHANGE = "appointment_change_requested"


def safe_handoff_reason(proposal: str) -> HandoffReason:
    try:
        return HandoffReason(proposal)
    except ValueError:
        # Model reasons may contain Customer data: never persist their raw text.
        return HandoffReason.MODEL_REQUEST


def handoff_confirmation(reason: HandoffReason, customer_message: str) -> str:
    text = "Vou encaminhar sua conversa para uma pessoa da equipe."
    if reason in {HandoffReason.APPOINTMENT_INTEREST, HandoffReason.APPOINTMENT_INTAKE_LIMIT}:
        text = "Vou encaminhar essas informações para a equipe confirmar a disponibilidade."
    if reason is HandoffReason.TECHNICAL_RISK:
        text = (
            "Se um procedimento estiver em andamento, pare e procure avaliação profissional. "
            "Se houver falta de ar ou sinais graves, procure atendimento médico urgente. " + text
        )
    if LiviaPersona().requires_identity_transparency(customer_message):
        text = REPLY_PHRASES[ReplyPhrase.IDENTITY] + " " + text
    return text
