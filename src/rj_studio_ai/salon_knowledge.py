"""Validated, versioned Salon Knowledge kept outside LLM adapters."""

import re
import unicodedata
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from yaml.constructor import ConstructorError


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects review-ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class SalonKnowledgeLoadError(RuntimeError):
    """Raised when a Salon Knowledge source cannot become trusted runtime data."""


class SalonKnowledgeNotLoaded(RuntimeError):
    """Raised when a caller selects facts before a successful load."""


class SalonKnowledgeCategory(StrEnum):
    IDENTITY = "identity"
    LOCATION = "location"
    CHANNEL = "channel"
    HOURS = "hours"
    SERVICE = "service"
    PRICE = "price"
    PROFESSIONAL = "professional"
    POLICY = "policy"
    HANDOFF_CONDITION = "handoff_condition"


class SalonKnowledgeStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"


class SalonKnowledgeFactType(StrEnum):
    OPERATIONAL_COMMERCIAL = "operational_commercial"
    TECHNICAL = "technical"


class TechnicalValidator(StrEnum):
    JOELMA = "Joelma"
    ROGERIO = "Rogério"


class SalonKnowledgeFact(BaseModel):
    """One reviewable institutional fact or rule about RJ Studio."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=3, pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: SalonKnowledgeCategory
    topic: str = Field(min_length=1)
    status: SalonKnowledgeStatus
    fact_type: SalonKnowledgeFactType
    statement: str = Field(min_length=1)
    source: str = Field(min_length=1)
    reviewed_at: date
    approved_by: str | None = Field(default=None, min_length=1)
    validated_by: tuple[TechnicalValidator, ...] = ()
    requires_human_consultation: bool = False
    mandatory_policy_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_approval_metadata(self) -> "SalonKnowledgeFact":
        if self.status is SalonKnowledgeStatus.APPROVED and self.approved_by is None:
            raise ValueError("approved_by is required for approved facts")
        if self.status is not SalonKnowledgeStatus.APPROVED and self.approved_by is not None:
            raise ValueError("approved_by is allowed only for approved facts")
        if self.fact_type is SalonKnowledgeFactType.TECHNICAL:
            if self.status is SalonKnowledgeStatus.APPROVED and not self.validated_by:
                raise ValueError("validated_by is required for approved technical facts")
        elif self.validated_by:
            raise ValueError("validated_by is allowed only for technical facts")
        if self.category is not SalonKnowledgeCategory.SERVICE and (
            self.requires_human_consultation or self.mandatory_policy_ids
        ):
            raise ValueError(
                "requires_human_consultation and mandatory_policy_ids are allowed only for services"
            )
        return self


class _SalonKnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1, le=1)
    facts: tuple[SalonKnowledgeFact, ...]


class SalonKnowledgeRepository:
    """Loads one YAML source atomically and selects approved relevant facts."""

    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path
        self._approved_facts: tuple[SalonKnowledgeFact, ...] | None = None

    def is_loaded(self) -> bool:
        return self._approved_facts is not None

    def load(self) -> tuple[SalonKnowledgeFact, ...]:
        self._approved_facts = None
        try:
            raw_document = yaml.load(
                self._source_path.read_text(encoding="utf-8"),
                Loader=_UniqueKeySafeLoader,
            )
        except (OSError, yaml.YAMLError) as error:
            raise SalonKnowledgeLoadError(
                "Salon Knowledge YAML is invalid or unavailable"
            ) from error
        try:
            document = _SalonKnowledgeDocument.model_validate(raw_document)
        except ValidationError as error:
            raise SalonKnowledgeLoadError(f"Salon Knowledge schema is invalid: {error}") from error

        facts_by_id = {fact.id: fact for fact in document.facts}
        if len(facts_by_id) != len(document.facts):
            raise SalonKnowledgeLoadError("Salon Knowledge contains duplicate id")
        self._validate_references(document.facts, facts_by_id)
        self._approved_facts = tuple(
            sorted(
                (fact for fact in document.facts if fact.status is SalonKnowledgeStatus.APPROVED),
                key=lambda fact: fact.id,
            )
        )
        return self._approved_facts

    def select(self, query: str, *, max_tokens: int) -> tuple[SalonKnowledgeFact, ...]:
        if self._approved_facts is None:
            raise SalonKnowledgeNotLoaded("Salon Knowledge has not loaded successfully")
        if max_tokens < 1:
            raise ValueError("Salon Knowledge selection budget must be positive")
        query_terms = _terms(query)
        if not query_terms:
            return ()

        approved_by_id = {fact.id: fact for fact in self._approved_facts}
        selected: list[SalonKnowledgeFact] = []
        selected_ids: set[str] = set()
        remaining_tokens = max_tokens
        for fact in self._approved_facts:
            if fact.id in selected_ids or not (_terms(fact.topic) & query_terms):
                continue
            closure = (fact,) + tuple(
                approved_by_id[policy_id]
                for policy_id in sorted(fact.mandatory_policy_ids)
                if policy_id not in selected_ids
            )
            closure_tokens = sum(_token_upper_bound(item) for item in closure)
            if closure_tokens > remaining_tokens:
                continue
            selected.extend(closure)
            selected_ids.update(item.id for item in closure)
            remaining_tokens -= closure_tokens
        return tuple(selected)

    @staticmethod
    def _validate_references(
        facts: tuple[SalonKnowledgeFact, ...],
        facts_by_id: dict[str, SalonKnowledgeFact],
    ) -> None:
        for fact in facts:
            for policy_id in fact.mandatory_policy_ids:
                policy = facts_by_id.get(policy_id)
                if policy is None:
                    raise SalonKnowledgeLoadError(
                        f"Salon Knowledge has invalid reference: {policy_id}"
                    )
                if policy.category is not SalonKnowledgeCategory.POLICY:
                    raise SalonKnowledgeLoadError(
                        f"Salon Knowledge reference is not a policy: {policy_id}"
                    )
                if (
                    fact.status is SalonKnowledgeStatus.APPROVED
                    and policy.status is not SalonKnowledgeStatus.APPROVED
                ):
                    raise SalonKnowledgeLoadError(
                        "Salon Knowledge approved service references unapproved policy: "
                        f"{policy_id}"
                    )


def _terms(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return {term for term in re.findall(r"[a-z0-9]+", without_accents) if len(term) >= 3}


def _token_upper_bound(fact: SalonKnowledgeFact) -> int:
    """Use UTF-8 bytes as a conservative upper bound for compact prompt tokens."""
    return len(_compact_context(fact).encode("utf-8"))


def _compact_context(fact: SalonKnowledgeFact) -> str:
    lines = [
        f"id: {fact.id}",
        f"category: {fact.category.value}",
        f"topic: {fact.topic}",
        f"type: {fact.fact_type.value}",
        f"statement: {fact.statement}",
    ]
    if fact.requires_human_consultation:
        lines.append("requires_human_consultation: true")
    if fact.mandatory_policy_ids:
        lines.append("mandatory_policy_ids: " + ",".join(sorted(fact.mandatory_policy_ids)))
    return "\n".join(lines)
