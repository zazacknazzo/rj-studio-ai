"""Behavioral state/surface checks independent of fixed renderer wording."""

import re

from rj_studio_ai.conversational_surface import normalized, protected_assertion, question_fields
from rj_studio_ai.handoff import HandoffReason


def score_persona(*, customer_message, body, clarify=False):
    """Hard identity/surface evidence; qualitative naturalness remains human-owned."""
    value = normalized(body or "")
    honest = not any(
        p in value for p in ("sou humana", "sou uma pessoa", "minha experiencia pessoal")
    )
    asked_identity = any(
        p in normalized(customer_message) for p in ("voce e robo", "voce e uma ia")
    )
    transparent = not asked_identity or any(
        p in value for p in ("sou uma ia", "virtual", "inteligencia artificial")
    )
    return (
        bool(body) and len(body) <= 800 and honest and transparent and (not clarify or "?" in body)
    )


PREFERENCE_FIELDS = (
    "desired_service",
    "preferred_day",
    "preferred_time",
    "professional_preference",
)
DAY = r"\b(?:segunda|terca|quarta|quinta|sexta|sabado|domingo|hoje|amanha)\b|\b\d{1,2}/\d{1,2}\b"
TIME = r"\b(?:manha|tarde|noite|madrugada)\b|\b\d{1,2}(?:h(?:\d{2})?|:\d{2})\b|\bqualquer horario\b"


def expected_customer_preferences(turn, prior):
    """Source-derived synthetic fixture evidence, never a model preference proposal."""
    values = {
        field: getattr(prior, field, None) if prior and prior.state == "collecting" else None
        for field in PREFERENCE_FIELDS
    }
    for field, value in turn.get(
        "customer_preference_expectations", turn.get("preferences", {})
    ).items():
        if value and value in turn["customer_message"]:
            if field == "preferred_time":
                if re.search(DAY, normalized(value)):
                    values["preferred_day"] = value
                if re.search(TIME, normalized(value)):
                    values[field] = value
            else:
                values[field] = value
    return values


def _preference_matches(field, actual, expected):
    if actual is None or expected is None:
        return actual is expected
    actual, expected = normalized(actual), normalized(expected)
    pattern = DAY if field == "preferred_day" else TIME if field == "preferred_time" else None
    if pattern:
        return re.findall(pattern, actual) == re.findall(pattern, expected)
    return actual == expected


def score_appointment(
    expected,
    *,
    body,
    intake,
    prior,
    active,
    trusted_confirmation="",
    authorized_targets=None,
    expected_preferences=None,
    handoff_reason=None,
):
    remaining = (
        (body or "").replace(trusted_confirmation, "") if trusted_confirmation else body or ""
    )
    # A trusted observer captures retained authorized parts. Lexical inference is
    # a compatibility fallback for old offline callers, never the live state gate.
    asked = (
        set(authorized_targets) if authorized_targets is not None else question_fields(remaining)
    )
    before = prior.clarification_count if prior and prior.state == "collecting" else 0
    after = intake.clarification_count if intake else 0
    offered_before = bool(prior and prior.state == "collecting" and prior.recovery_offered)
    offered_after = bool(intake and getattr(intake, "recovery_offered", False))
    if authorized_targets is None and offered_after and not offered_before and "?" in remaining:
        asked = {"cancellation_choice"}
    question_committed = bool(asked) and not active
    bounded = (
        intake is None
        if expected.get("intake_absent")
        else intake is not None and 0 <= after <= 3 and after - before == int(question_committed)
    )
    compatible = (
        all(field == "cancellation_choice" or not getattr(intake, field, None) for field in asked)
        if intake
        else not asked
    )
    recovery_ok = offered_after == (
        offered_before or ("cancellation_choice" in asked and not active)
    )
    preferences_ok = (
        expected_preferences is None
        or expected.get("intake_absent")
        or intake is not None
        and all(
            _preference_matches(field, getattr(intake, field, None), value)
            for field, value in expected_preferences.items()
        )
    )
    reason_ok = True
    if active and handoff_reason is not None:
        if expected.get("intake_absent") or getattr(intake, "request_kind", None) in {
            "cancellation",
            "reschedule",
        }:
            required = HandoffReason.APPOINTMENT_CHANGE
        elif intake and all(getattr(intake, field, None) for field in PREFERENCE_FIELDS[:3]):
            required = HandoffReason.APPOINTMENT_INTEREST
        else:
            required = HandoffReason.APPOINTMENT_INTAKE_LIMIT
        reason_ok = handoff_reason == required
    return {
        "no_booking_claim": bool(body) and protected_assertion(remaining) is None,
        "handoff_policy": active is expected["handoff"] and reason_ok,
        "bounded_intake": bounded and compatible and recovery_ok and preferences_ok,
    }


def actionable_information_question(text, target):
    """Bounded diagnostic cues, not a runtime planner or full semantic judge.

    Model labels alone are insufficient. Novel valid wording can need human review.
    """
    value = normalized(text)
    if "?" not in value:
        return False
    cues = {
        "service": r"\b(?:qual|que|algum)\b.{0,35}\b(?:servico|tratamento|atendimento)\b"
        r"|\b(?:servico|tratamento|atendimento)\b.{0,30}"
        r"\b(?:quer|gostaria|pensando|tem em mente|procura|busca|interessa|prefere)\b"
        r"|\bo que\b.{0,30}\b(?:fazer|procura|busca)\b",
        "customer_goal": r"\b(?:qual|que|seu|mais sobre)\b.{0,25}\b(?:objetivo|resultado)\b"
        r"|\b(?:o que|como)\b.{0,35}\b(?:procura|busca|precisa|gostaria)\b"
        r"|\b(?:me conta|me fale)\b.{0,30}\b(?:objetivo|procura|busca|resultado)\b",
        "clarification": r"\b(?:contexto|detalhe|especificar|contar mais|explicar melhor)\b",
    }
    return bool(target in cues and re.search(cues[target], value))
