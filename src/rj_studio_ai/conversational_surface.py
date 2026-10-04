"""Small protected-assertion veto, not a conversational planner or semantic proof."""

import re
import unicodedata


def normalized(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)
    )


# Defense in depth for known critical assertions. Never used to choose wording,
# authorize a fact/action, or claim exhaustive semantic detection.
_ASSERTIONS = (
    (
        "financial",
        r"\b(?:custa|cobramos|concedo|ganha desconto|tem desconto|desconto autorizado|"
        r"promocao ativa|aceitamos pagamento|pagamento confirmado|reais|dolares)\b",
    ),
    ("salon_operation", r"\b(?:oferecemos|nosso endereco|nosso telefone)\b"),
    ("official_hours", r"\b(?:abrimos|fechamos|funcionamos|atendemos das)\b"),
    (
        "availability_or_action",
        r"\b(?:agendei|cancelei|remarquei|reservamos|temos vaga|temos horario|"
        r"pode vir)\b|\b(?:vaga|horario|agendamento|cancelamento|pagamento|profissional)\b.{0,35}"
        r"\b(?:confirmad\w*|reservad\w*|disponivel|realizad\w*)\b",
    ),
    (
        "policy_or_technical",
        r"\b(?:nossa politica|garantimos|resultado garantido|"
        r"nao causa dano|pode continuar a quimica|pode fazer com seguranca)\b",
    ),
)


def protected_assertion(text: str) -> str | None:
    """Veto known untrusted assertions. Caller must first remove trusted segments."""
    value = normalized(text)
    preference_question = bool(question_fields(text) & {"preferred_day", "preferred_time"})
    numeric_residue = (
        re.sub(r"\b\d{1,2}(?:h(?:\d{2})?|:\d{2})\b|\b\d{1,2}/\d{1,2}\b", "", value)
        if preference_question
        else value
    )
    if re.search(r"[$€£%]|\b(?:usd|brl)\b", value) or re.search(r"\d", numeric_residue):
        return "untrusted_numeric_fact"
    return next((code for code, pattern in _ASSERTIONS if re.search(pattern, value)), None)


def question_fields(text: str) -> set[str]:
    """Bounded undeclared preference/recovery cues, not wording selection or full NLP."""
    value = normalized(text)
    if "?" not in value:
        return set()
    concepts = {
        "desired_service": r"\b(?:qual|que|algum)\b.{0,20}\b(?:servico|tratamento)\b|"
        r"\bo que\b.{0,12}\b(?:quer|gostaria|pretende)\b.{0,8}\bfazer\b",
        "preferred_day": r"\b(?:qual|que|algum)\b.{0,20}\b(?:dia|data)\b|"
        r"\b(?:dia|data)\b.{0,20}\b(?:prefere|melhor|funciona)\b|"
        r"\bquando\b.{0,20}\b(?:prefere|pode|quer|pensando)\b",
        "preferred_time": r"\b(?:qual|que|algum)\b.{0,20}\b(?:horario|hora|periodo)\b|"
        r"\b(?:prefere|melhor|funciona)\b.{0,35}(?:\b(?:horario|manha|tarde|noite)\b|"
        r"\b\d{1,2}(?:h(?:\d{2})?|:\d{2})\b)",
        "cancellation_choice": r"\b(?:quer|gostaria|prefere|topa|aceita|vamos|tentar)\b.{0,45}"
        r"\b(?:outro dia|outra data|remarcar|reagendar|mudar a data|trocar o dia)\b",
        "professional_preference": r"\b(?:qual|que|algum|prefere|preferencia)\b.{0,20}"
        r"\b(?:profissional|pessoa)\b|\bprofissional\b.{0,20}\b(?:prefere|preferencia)\b",
    }
    return {field for field, pattern in concepts.items() if re.search(pattern, value)}
