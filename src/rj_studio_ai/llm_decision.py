"""Validated, provider-neutral proposal returned by an LLM generation."""

from enum import StrEnum
from typing import Any, Literal

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
    """One proposed factual value; trusted rendering replaces it from approved data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_type: CriticalFactType
    value: StrictStr = Field(min_length=1, max_length=800)
    knowledge_ref: StrictStr = Field(min_length=3, pattern=r"^[a-z0-9][a-z0-9-]*$")


class ReplyPhrase(StrEnum):
    GREETING = "greeting"
    FORMAL_GREETING = "formal_greeting"
    INTRODUCTION = "introduction"
    HELP = "help"
    INFORMATION = "information"
    SERVICE_QUESTION = "service_question"
    DETAIL_QUESTION = "detail_question"
    CLARIFICATION = "clarification"
    IDENTITY = "identity"
    CONFIRMATION = "confirmation"
    ACKNOWLEDGEMENT = "acknowledgement"
    WARM_ACKNOWLEDGEMENT = "warm_acknowledgement"
    APPOINTMENT_CONTINUATION = "appointment_continuation"
    SERVICE_CONTINUATION = "service_continuation"
    PRICE_SERVICE_QUESTION = "price_service_question"
    DISCOUNT_SERVICE_QUESTION = "discount_service_question"


class PhraseReplyPart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["phrase"]
    phrase: ReplyPhrase


class FactReplyPart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["fact"]
    knowledge_ref: StrictStr = Field(min_length=3, pattern=r"^[a-z0-9][a-z0-9-]*$")


class ConversationalPurpose(StrEnum):
    ACKNOWLEDGEMENT = "acknowledgement"
    SOCIAL = "social"
    CLARIFICATION = "clarification"
    QUESTION = "question"
    COMMERCIAL_CONTINUATION = "commercial_continuation"
    CTA = "cta"
    RECOVERY = "recovery"
    TRANSITION = "transition"


class PreferenceTarget(StrEnum):
    SERVICE = "desired_service"
    DAY = "preferred_day"
    TIME = "preferred_time"
    PROFESSIONAL = "professional_preference"
    CANCELLATION = "cancellation_choice"


class InformationTarget(StrEnum):
    SERVICE = "service"
    CUSTOMER_GOAL = "customer_goal"
    CLARIFICATION = "clarification"


class ConversationalReplyPart(BaseModel):
    """Untrusted bounded wording. Purpose/targets confer no action authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["conversation"]
    purpose: ConversationalPurpose
    text: StrictStr = Field(min_length=1, max_length=400)
    targets: tuple[PreferenceTarget, ...] = Field(default=(), max_length=4)

    information_targets: tuple[InformationTarget, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def coherent_targets(self):
        if not self.text.strip() or any(ord(c) < 32 and c not in "\n\t" for c in self.text):
            raise ValueError("invalid conversational surface")
        if self.targets and self.information_targets:
            raise ValueError("question scopes must be separate")
        if len(set(self.information_targets)) != len(self.information_targets):
            raise ValueError("duplicate information target")
        if self.information_targets and self.purpose not in {
            ConversationalPurpose.QUESTION,
            ConversationalPurpose.CLARIFICATION,
        }:
            raise ValueError("only a general question can target an information gap")
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("duplicate question target")
        if self.targets and self.purpose not in {
            ConversationalPurpose.QUESTION,
            ConversationalPurpose.CLARIFICATION,
            ConversationalPurpose.RECOVERY,
        }:
            raise ValueError("only a question/recovery can target a preference")
        if self.purpose is ConversationalPurpose.RECOVERY and self.targets != (
            PreferenceTarget.CANCELLATION,
        ):
            raise ValueError("recovery must declare its persisted opportunity")
        return self


ReplyPart = PhraseReplyPart | FactReplyPart | ConversationalReplyPart


class AppointmentPreferences(BaseModel):
    """Untrusted exact excerpts of Customer preferences, never salon facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    desired_service: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    preferred_day: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    preferred_time: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    professional_preference: StrictStr | None = Field(default=None, min_length=1, max_length=120)


class NextConversationalAction(StrEnum):
    ANSWER_ONLY = "answer_only"
    CLARIFY = "clarify"
    CONTINUE_CONVERSATION = "continue_conversation"
    SOCIAL_RESPONSE = "social_response"
    REQUEST_HUMAN_ATTENTION = "request_human_attention"


class LLMDecision(BaseModel):
    """A structurally valid but still untrusted proposal for one inbound Message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    surface: Literal["legacy", "agentic"] = "legacy"
    # Planning/observation only. Never grants an operational effect.
    next_action: NextConversationalAction | None = None
    intents: tuple[Intent, ...] = Field(min_length=1)
    reply_text: StrictStr = Field(min_length=1, max_length=MAX_REPLY_TEXT_CHARACTERS)
    # Empty only for older proposals and deterministic fixed replies. Free text
    # is never used to render a probabilistic decision, even when parts are empty.
    reply_parts: tuple[ReplyPart, ...] = Field(default=(), max_length=8)
    uncertainty: UncertaintyLevel
    knowledge_refs: tuple[StrictStr, ...]
    critical_claims: tuple[CriticalFactualClaim, ...]
    handoff: StrictBool
    handoff_reason: StrictStr | None = Field(max_length=320)
    appointment_preferences: AppointmentPreferences | None = None

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
    for part in decision.reply_parts:
        if isinstance(part, FactReplyPart) and part.knowledge_ref not in declared_references:
            raise StructuredDecisionValidationError(
                "Fact reply part must declare its knowledge reference"
            )
    return decision


def decision_json_schema() -> dict[str, Any]:
    """Return the provider-agnostic JSON schema for structured output adapters."""
    schema = LLMDecision.model_json_schema()
    # The Python contract still reads legacy proposals, but all new provider
    # requests require the typed rendering plan explicitly (possibly empty).
    schema["properties"]["reply_parts"].pop("default", None)
    schema["properties"]["appointment_preferences"].pop("default", None)
    preferences = schema["$defs"]["AppointmentPreferences"]
    preferences["required"] = list(preferences["properties"])
    for field in preferences["properties"].values():
        field.pop("default", None)
    conversational = schema["$defs"]["ConversationalReplyPart"]
    for field in ("targets", "information_targets"):
        conversational["properties"][field].pop("default", None)
    conversational["required"] = list(conversational["properties"])
    schema["properties"]["surface"].pop("default", None)
    schema["properties"]["next_action"].pop("default", None)
    schema["required"] = list(schema["properties"])
    return schema


def uses_agentic_surface(decision: LLMDecision) -> bool:
    return decision.surface == "agentic" or any(
        isinstance(part, ConversationalReplyPart) for part in decision.reply_parts
    )


def _is_knowledge_id(value: str) -> bool:
    import re

    return re.fullmatch(r"[a-z0-9][a-z0-9-]*", value) is not None
