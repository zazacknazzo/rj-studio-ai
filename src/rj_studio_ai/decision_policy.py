"""Deterministic grounding and Human Handoff policy for untrusted LLM decisions."""

import re
import unicodedata
from dataclasses import dataclass

from rj_studio_ai.llm_decision import CriticalFactType, LLMDecision
from rj_studio_ai.salon_knowledge import (
    SalonKnowledgeCategory,
    SalonKnowledgeFact,
    SalonKnowledgeStatus,
)


class DecisionPolicyViolation(ValueError):
    """An LLM proposal cannot safely become a customer-visible AI Reply."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class ValidatedDecision:
    """Provider-neutral result after deterministic truth and policy checks."""

    reply_text: str
    effective_handoff: bool
    handoff_reason: str | None
    mandatory_handoff: bool


class DecisionPolicy:
    """Turn one untrusted proposal into a grounded decision or reject it safely."""

    def evaluate(
        self,
        decision: LLMDecision,
        *,
        selected_knowledge: tuple[SalonKnowledgeFact, ...],
        active_handoff: bool = False,
        customer_message: str | None = None,
    ) -> ValidatedDecision:
        trusted_by_id = {
            fact.id: fact
            for fact in selected_knowledge
            if fact.status is SalonKnowledgeStatus.APPROVED
        }
        canonical_statements = self._validate_claims(decision, trusted_by_id)
        if canonical_statements:
            rendered_reply = "\n\n".join(canonical_statements)
            if _canonical_text(decision.reply_text) != _canonical_text(rendered_reply):
                raise DecisionPolicyViolation(
                    "Customer-visible critical text conflicts with trusted knowledge",
                    error_code="grounding_rejection",
                )
        else:
            rendered_reply = decision.reply_text
            if _contains_unstructured_critical_assertion(rendered_reply):
                raise DecisionPolicyViolation(
                    "Customer-visible critical text has no validated claim",
                    error_code="grounding_rejection",
                )
            if (
                customer_message is not None
                and _is_critical_request(customer_message)
                and not _is_safe_clarification(rendered_reply)
            ):
                raise DecisionPolicyViolation(
                    "Critical request has neither validated claims nor a safe clarification",
                    error_code="grounding_rejection",
                )

        mandatory_reason = _mandatory_handoff_reason(
            tuple(trusted_by_id.values()),
            active_handoff=active_handoff,
        )
        mandatory_handoff = mandatory_reason is not None
        effective_handoff = mandatory_handoff or decision.handoff
        handoff_reason = mandatory_reason
        if handoff_reason is None and decision.handoff:
            handoff_reason = "model_requested_handoff"
        return ValidatedDecision(
            reply_text=rendered_reply,
            effective_handoff=effective_handoff,
            handoff_reason=handoff_reason,
            mandatory_handoff=mandatory_handoff,
        )

    @staticmethod
    def _validate_claims(
        decision: LLMDecision,
        trusted_by_id: dict[str, SalonKnowledgeFact],
    ) -> tuple[str, ...]:
        expected_categories = {
            CriticalFactType.PRICE: SalonKnowledgeCategory.PRICE,
            CriticalFactType.HOURS: SalonKnowledgeCategory.HOURS,
            CriticalFactType.PROFESSIONAL: SalonKnowledgeCategory.PROFESSIONAL,
            CriticalFactType.SERVICE: SalonKnowledgeCategory.SERVICE,
            CriticalFactType.POLICY: SalonKnowledgeCategory.POLICY,
        }
        seen_references: set[str] = set()
        statements: list[str] = []
        for claim in decision.critical_claims:
            if claim.knowledge_ref in seen_references:
                raise DecisionPolicyViolation(
                    "Critical claims contain a duplicate knowledge reference",
                    error_code="invalid_critical_claim",
                )
            seen_references.add(claim.knowledge_ref)
            fact = trusted_by_id.get(claim.knowledge_ref)
            if fact is None:
                raise DecisionPolicyViolation(
                    "Critical claim has no selected approved knowledge",
                    error_code="invalid_critical_claim",
                )
            expected_category = expected_categories.get(claim.fact_type)
            if expected_category is None or fact.category is not expected_category:
                raise DecisionPolicyViolation(
                    "Critical claim type does not match trusted knowledge",
                    error_code="invalid_critical_claim",
                )
            if _canonical_text(claim.value) != _canonical_text(fact.statement):
                raise DecisionPolicyViolation(
                    "Critical claim value does not match the canonical trusted value",
                    error_code="invalid_critical_claim",
                )
            statements.append(fact.statement)
        for reference in seen_references:
            fact = trusted_by_id[reference]
            if fact.category is not SalonKnowledgeCategory.SERVICE:
                continue
            if not set(fact.mandatory_policy_ids).issubset(seen_references):
                raise DecisionPolicyViolation(
                    "Service claim omits a selected mandatory policy",
                    error_code="invalid_critical_claim",
                )
        return tuple(statements)


def _mandatory_handoff_reason(
    selected_knowledge: tuple[SalonKnowledgeFact, ...],
    *,
    active_handoff: bool,
) -> str | None:
    if active_handoff:
        return "active_handoff"
    if any(
        fact.category is SalonKnowledgeCategory.SERVICE and fact.requires_human_consultation
        for fact in selected_knowledge
    ):
        return "service_requires_human_consultation"
    if any(
        fact.category is SalonKnowledgeCategory.HANDOFF_CONDITION for fact in selected_knowledge
    ):
        return "approved_handoff_condition"
    return None


def _canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_accents.split())


def _contains_unstructured_critical_assertion(reply_text: str) -> bool:
    normalized = _search_text(reply_text)
    patterns = (
        r"r\s*\$\s*\d",
        r"\b\d+(?:[.,]\d+)?\s*reais?\b",
        r"\b(?:custa|fica\s+por|sai\s+por)\b",
        r"\b(?:[01]?\d|2[0-3])\s*(?::\s*[0-5]\d|h(?:oras?)?)\b",
        r"\b(?:temos?|ha|esta|ficou)\s+(?:um\s+)?horario\b",
        r"\b(?:horario|agenda)\s+(?:esta\s+)?disponivel\b",
        r"\b(?:vaga|disponibilidade)\s+(?:para|na|no)\b",
        r"\b(?:consigo\s+agendar|agendei|reservei|ficou\s+agendad[ao]|confirmado\s+para)\b",
        r"\b(?:a|o)\s+profissional\s+[a-z]",
        r"\b(?:fazemos|oferecemos|trabalhamos\s+com)\b",
        r"\b(?:nossa\s+politica|permitimos|nao\s+permitimos|e\s+obrigatorio)\b",
        r"\b(?:abrimos|fechamos|funcionamos)\b",
    )
    if any(re.search(pattern, normalized) for pattern in patterns):
        return True
    return (
        re.search(
            r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][\wÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç-]+\s+"
            r"(?:faz|realiza|atende)\b",
            reply_text,
        )
        is not None
    )


def _is_critical_request(customer_message: str) -> bool:
    normalized = _search_text(customer_message)
    patterns = (
        r"\b(?:quanto\s+custa|preco|valor|paguei|reais?)\b",
        r"r\s*\$",
        r"\b(?:horario|abre|abrem|fecha|fecham|funciona|funcionam)\b",
        r"\b(?:profissional|quem\s+(?:faz|atende))\b",
        r"\b(?:voces?\s+(?:faz|fazem|oferece|oferecem|tem)|servico)\b",
        r"\b(?:politica|cancelamento|atraso)\b",
        r"\b(?:disponivel|disponibilidade|vaga|agendar|agendamento|marcar)\b",
        r"\btem\s+horario\b",
    )
    if any(re.search(pattern, normalized) for pattern in patterns):
        return True
    return (
        re.search(
            r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][\wÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç-]+\s+"
            r"(?:faz|realiza|atende)\b",
            customer_message,
        )
        is not None
    )


def _is_safe_clarification(reply_text: str) -> bool:
    clauses = [
        clause.strip() for clause in re.split(r"[.?!]+", _search_text(reply_text)) if clause.strip()
    ]
    if not clauses:
        return False
    safe_clauses = (
        r"(?:posso|preciso|vou)\s+(?:confirmar|verificar)\s+.{0,100}\s+com\s+a\s+equipe"
        r"(?:\s+do\s+rj\s+studio)?",
        r"(?:ainda\s+)?nao\s+(?:tenho|consigo\s+confirmar)\s+.{1,120}",
        r"(?:qual|quando|onde)\s+.{1,120}",
        r"(?:voce\s+pode|pode\s+me)\s+.{1,120}",
    )
    return all(any(re.fullmatch(pattern, clause) for pattern in safe_clauses) for clause in clauses)
