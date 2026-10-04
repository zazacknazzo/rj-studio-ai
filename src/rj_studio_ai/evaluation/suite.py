"""Versioned synthetic-only case index. Never loads the runtime salon facts or .env."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from rj_studio_ai.evaluation.records import (
    CaseContract,
    CheckContract,
    Identifier,
    RecordModel,
    check_privacy,
    fingerprint,
)
from rj_studio_ai.llm_decision import LLMDecision

Kind = Literal["intent", "persona", "grounding", "appointment", "handoff", "context"]


class Source(RecordModel):
    file: str = Field(pattern=r"^[a-z-]+\.yaml$")
    kind: Kind
    categories: tuple[Identifier, ...]


class Manifest(RecordModel):
    version: Literal[1]
    suite_id: Literal["v1"]
    sources: tuple[Source, ...]
    critical_scenarios: dict[Identifier, tuple[Identifier, ...]]


@dataclass(frozen=True)
class EvalCase:
    kind: Kind
    data: dict
    facts: dict
    categories: tuple[str, ...]
    contract: CaseContract


@dataclass(frozen=True)
class EvalSuite:
    cases: tuple[EvalCase, ...]
    critical_scenarios: dict
    rubric: dict
    digest: str
    knowledge_digest: str


_CASE_FIELDS = {
    "intent": {"id", "customer_message", "expected_intents", "forbidden_claims"},
    "persona": {"id", "customer_message", "checks"},
    "grounding": {
        "id",
        "customer_message",
        "selected_facts",
        "proposal",
        "expected",
        "live_expected",
        "live_expected_intents",
    },
    "appointment": {"id", "turns"},
    "handoff": {"id", "turns"},
    "context": {"id", "scenario", "expected"},
}
_CHECKS = {
    "intent": {"decision_contract": ("intent", False)},
    "persona": {"persona_surface": ("persona", False)},
    "grounding": {
        "trusted_facts": ("grounding", True),
        "handoff_policy": ("handoff", True),
    },
    "appointment": {
        "no_booking_claim": ("grounding", True),
        "handoff_policy": ("handoff", True),
        "bounded_intake": ("context", True),
    },
    "handoff": {"durable_handoff": ("handoff", True), "suppression": ("handoff", True)},
    "context": {"context_bounds": ("context", False)},
}

_CRITICAL_SCENARIOS = {
    "invented_price",
    "altered_approved_price",
    "unauthorized_discount",
    "invented_hours_or_availability",
    "false_booking",
    "technical_risk_without_handoff",
    "human_request_without_handoff",
    "cancel_reschedule_without_handoff",
    "injection_altering_facts",
    "invalid_reference",
    "omitted_mandatory_policy",
}


def fixture_decision(**overrides) -> LLMDecision:
    """Merge a partial synthetic proposal and validate its entire existing typed AST."""
    return LLMDecision.model_validate(
        {
            "intents": ["other"],
            "reply_text": "Untrusted fixture proposal",
            "reply_parts": [{"kind": "phrase", "phrase": "detail_question"}],
            "uncertainty": "low",
            "knowledge_refs": [],
            "critical_claims": [],
            "handoff": False,
            "handoff_reason": None,
            **overrides,
        }
    )


def grounding_relevance_matches(expected, *, facts, reply_text) -> bool:
    """Bound displayed approved statements, not declarations absent from the reply."""
    allowed = expected.get("allowed_fact_ids")
    if allowed is None:
        return True
    rendered = {fact.id for fact in facts if reply_text and fact.statement in reply_text}
    return rendered <= set(allowed)


def _validate_case(kind, data):
    if data.keys() - _CASE_FIELDS[kind] or not {"id"} <= data.keys():
        raise ValueError("eval_unknown_or_missing_fixture_field")
    required = {
        "intent": {"customer_message", "expected_intents"},
        "persona": {"customer_message", "checks"},
        "grounding": {"customer_message", "selected_facts", "proposal", "expected"},
        "appointment": {"turns"},
        "handoff": {"turns"},
        "context": {"scenario", "expected"},
    }
    if not required[kind] <= data.keys():
        raise ValueError("eval_missing_fixture_field")
    if kind in {"grounding", "context"}:
        expected_fields = (
            {"contains", "excludes", "handoff"}
            if kind == "grounding"
            else {"history_count", "incomplete"}
        )
        optional_fields = {"allowed_fact_ids"} if kind == "grounding" else set()
        if (
            not expected_fields <= data["expected"].keys()
            or data["expected"].keys() - expected_fields - optional_fields
        ):
            raise ValueError("eval_unknown_or_missing_expectation_field")
    if kind == "grounding":
        if "live_expected_intents" in data:
            fixture_decision(intents=data["live_expected_intents"])
        if "live_expected" in data:
            _validate_case(
                kind,
                {k: v for k, v in data.items() if k != "live_expected"}
                | {"expected": data["live_expected"]},
            )
        expected = data["expected"]
        if expected["handoff"] is not None and type(expected["handoff"]) is not bool:
            raise ValueError("eval_invalid_handoff_expectation")
        if "allowed_fact_ids" in expected:
            allowed = expected["allowed_fact_ids"]
            if (
                not isinstance(allowed, list)
                or any(not isinstance(identifier, str) for identifier in allowed)
                or len(set(allowed)) != len(allowed)
                or not set(allowed) <= set(data["selected_facts"])
            ):
                raise ValueError("eval_invalid_relevance_expectation")
        fixture_decision(**data["proposal"])
    elif kind == "intent":
        fixture_decision(intents=data["expected_intents"])
    if kind in {"appointment", "handoff"}:
        for turn in data["turns"]:
            if (
                turn.keys()
                - {
                    "customer_message",
                    "preferences",
                    "expected",
                    "expected_intents",
                    "adversarial_reply_text",
                    "action",
                }
                or not {"customer_message", "expected"} <= turn.keys()
            ):
                raise ValueError("eval_unknown_or_missing_fixture_field")
            expected_fields = (
                {"active", "suppressed"}
                if kind == "handoff"
                else {"handoff", "clarification_count", "contains", "intake_absent"}
            )
            if turn["expected"].keys() - expected_fields:
                raise ValueError("eval_unknown_fixture_field")
            fixture_decision(
                intents=turn.get("expected_intents", ["other"]),
                reply_text=turn.get("adversarial_reply_text", "Untrusted fixture proposal"),
                appointment_preferences=turn.get("preferences"),
            )
            if "action" in turn and (
                kind != "handoff" or turn["action"] not in {"restart", "release"}
            ):
                raise ValueError("eval_invalid_fixture_action")
    if kind == "context" and data["scenario"] not in {"bounded", "expired", "pending"}:
        raise ValueError("eval_unknown_context_scenario")


def _safe_yaml(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    check_privacy(data)
    return data


def load_suite(path: Path) -> EvalSuite:
    manifest = Manifest.model_validate(_safe_yaml(path / "suite.yaml"))
    if set(manifest.critical_scenarios) != _CRITICAL_SCENARIOS:
        raise ValueError("eval_missing_critical_scenario")
    cases = []
    documents = []
    for source in manifest.sources:
        document = _safe_yaml(path / source.file)
        if document.get("version") != 1 or document.get("source_type") != "synthetic":
            raise ValueError("eval_requires_synthetic_provenance")
        if document.keys() - {
            "version",
            "source_type",
            "cases",
            "facts",
            "spec",
            "gate_owner",
            "forbidden_claims",
        }:
            raise ValueError("eval_unknown_fixture_field")
        documents.append(document)
        for fact in document.get("facts", {}).values():
            if fact.keys() - {
                "category",
                "statement",
                "requires_human_consultation",
                "mandatory_policy_ids",
            }:
                raise ValueError("eval_unknown_fixture_fact_field")
        for data in document["cases"]:
            _validate_case(source.kind, data)
            if source.kind == "grounding" and any(
                identifier not in document.get("facts", {}) for identifier in data["selected_facts"]
            ):
                raise ValueError("eval_unknown_selected_fact")
            contract = CaseContract(
                case_id=data["id"],
                turns=len(data.get("turns", [data])),
                checks={
                    key: CheckContract(metric=metric, critical=critical)
                    for key, (metric, critical) in _CHECKS[source.kind].items()
                    if not (
                        source.kind == "grounding"
                        and key == "handoff_policy"
                        and data["expected"]["handoff"] is None
                    )
                },
            )
            cases.append(
                EvalCase(
                    kind=source.kind,
                    data=data,
                    facts=document.get("facts", {}),
                    categories=source.categories,
                    contract=contract,
                )
            )
    by_id = {case.contract.case_id: case for case in cases}
    if len(by_id) != len(cases) or len(cases) < 28:
        raise ValueError("eval_invalid_suite_case_count")
    for identifiers in manifest.critical_scenarios.values():
        if not identifiers or any(identifier not in by_id for identifier in identifiers):
            raise ValueError("eval_missing_critical_case")
        if any(not any(c.critical for c in by_id[i].contract.checks.values()) for i in identifiers):
            raise ValueError("eval_missing_critical_check")
    rubric = _safe_yaml(path / "naturalness-rubric.yaml")
    if rubric.get("version") != "livia-naturalness-v1" or set(rubric.get("dimensions", {})) != {
        "warmth",
        "whatsapp_clarity",
        "persona_stability",
        "contextual_fit",
    }:
        raise ValueError("eval_invalid_rubric")
    return EvalSuite(
        cases=tuple(cases),
        critical_scenarios=manifest.critical_scenarios,
        rubric=rubric,
        digest=fingerprint([manifest.model_dump(), documents, rubric]),
        knowledge_digest=fingerprint([case.facts for case in cases]),
    )
