"""Validated, provider-neutral proposal returned by an LLM generation."""

from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationError,
    model_validator,
)

MAX_OUTPUT_TOKENS = 200
MAX_REPLY_TEXT_CHARACTERS = 800


class StructuredDecisionValidationError(ValueError):
    """An untrusted provider proposal does not satisfy the V1 decision contract."""


class Intent(StrEnum):
    GREETING = "greeting"
    SERVICE_INFORMATION = "service_information"
    PRICE = "price"
    PROFESSIONAL = "professional"
    HOURS = "hours"
    LOCATION = "location"
    TECHNICAL_GUIDANCE = "technical_guidance"
    APPOINTMENT_INTEREST = "appointment_interest"
    APPOINTMENT_CHANGE = "appointment_change"
    COMPLAINT = "complaint"
    PROMOTION_OR_DISCOUNT = "promotion_or_discount"
    HUMAN_REQUEST = "human_request"
    OTHER = "other"


class UncertaintyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CriticalFactType(StrEnum):
    PRICE = "price"
    HOURS = "hours"
    PROFESSIONAL = "professional"
    SERVICE = "service"
    POLICY = "policy"
    AVAILABILITY = "availability"


class CriticalFactualClaim(BaseModel):
    """One factual value proposed by the model; Ticket 09 will enforce it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_type: CriticalFactType
    value: StrictStr = Field(
        min_length=1,
        max_length=800,
        description="Exact canonical statement proposed from the selected Salon Knowledge fact.",
    )
    knowledge_ref: StrictStr = Field(
        min_length=3,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="Stable identifier of the selected approved Salon Knowledge fact.",
    )


class LLMDecision(BaseModel):
    """A structurally valid but still untrusted proposal for one inbound Message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intents: tuple[Intent, ...] = Field(min_length=1)
    reply_text: StrictStr = Field(min_length=1, max_length=MAX_REPLY_TEXT_CHARACTERS)
    uncertainty: UncertaintyLevel
    knowledge_refs: tuple[StrictStr, ...]
    critical_claims: tuple[CriticalFactualClaim, ...]
    handoff: StrictBool
    handoff_reason: StrictStr | None = Field(max_length=320)

    @model_validator(mode="after")
    def validate_internal_consistency(self) -> "LLMDecision":
        if not self.reply_text.strip():
            raise ValueError("reply_text must not be blank")
        if len(set(self.intents)) != len(self.intents):
            raise ValueError("intents must not contain duplicates")
        if len(set(self.knowledge_refs)) != len(self.knowledge_refs):
            raise ValueError("knowledge_refs must not contain duplicates")
        for reference in self.knowledge_refs:
            if not _is_knowledge_id(reference):
                raise ValueError("knowledge_refs contains an invalid identifier")
        if self.handoff and (self.handoff_reason is None or not self.handoff_reason.strip()):
            raise ValueError("handoff_reason is required when handoff is proposed")
        if not self.handoff and self.handoff_reason is not None:
            raise ValueError("handoff_reason is allowed only when handoff is proposed")
        return self


def validate_llm_decision(
    payload: object,
    *,
    allowed_knowledge_refs: set[str],
) -> LLMDecision:
    """Parse an LLM proposal without letting provider dictionaries into the core."""
    if not isinstance(payload, dict):
        raise StructuredDecisionValidationError("Structured decision must be an object")
    try:
        decision = LLMDecision.model_validate(payload)
    except ValidationError as error:
        raise StructuredDecisionValidationError(
            "Structured decision has an invalid schema"
        ) from error

    declared_references = set(decision.knowledge_refs)
    if not declared_references.issubset(allowed_knowledge_refs):
        raise StructuredDecisionValidationError(
            "Structured decision references unavailable knowledge"
        )
    for claim in decision.critical_claims:
        if claim.knowledge_ref not in declared_references:
            raise StructuredDecisionValidationError(
                "Critical factual claim must declare its knowledge reference"
            )
    return decision


def decision_json_schema() -> dict[str, Any]:
    """Return the provider-agnostic JSON schema for structured output adapters."""
    return LLMDecision.model_json_schema()


def _is_knowledge_id(value: str) -> bool:
    import re

    return re.fullmatch(r"[a-z0-9][a-z0-9-]*", value) is not None
