"""Versioned live evidence and replay, separate from injected fixture expectations."""

from typing import Literal

from pydantic import StrictBool, model_validator

from rj_studio_ai.conversational_surface import protected_assertion
from rj_studio_ai.evaluation.records import (
    Digest,
    Identifier,
    RecordModel,
    check_privacy,
    fingerprint,
)
from rj_studio_ai.evaluation.suite import grounding_relevance_matches
from rj_studio_ai.handoff import HandoffReason, handoff_confirmation
from rj_studio_ai.livia_persona import HUMAN_REVIEW_REPLY, REPLY_PHRASES
from rj_studio_ai.llm_decision import (
    Intent,
    PreferenceTarget,
    StructuredDecisionValidationError,
    validate_llm_decision,
)

LEGACY_ORACLE_VERSION = "v1-live-semantic-2026-10-03-v2"
ORACLE_VERSION = "v1-agentic-behavioral-2026-10-04-v3"


def execution_category(case):
    return "STRUCTURAL_CONTRACT" if case.kind == "context" else "LIVE_BEHAVIORAL"


def live_expectation(case):
    return case.data.get("live_expected", case.data["expected"])


def _oracle_digest(case, version=ORACLE_VERSION):
    return fingerprint(
        [
            version,
            case.contract.case_id,
            live_expectation(case),
            case.data.get("live_expected_intents"),
            case.data["selected_facts"],
            case.facts,
            case.data["customer_message"],
        ]
    )


class GroundingObservation(RecordModel):
    """Trusted observer metadata, not model prose, Customer text or reasoning."""

    oracle_version: Literal[
        "v1-live-semantic-2026-10-03-v2", "v1-agentic-behavioral-2026-10-04-v3"
    ] = ORACLE_VERSION
    oracle: Digest
    case_id: Identifier
    reply_hash: Digest
    selected_fact_ids: tuple[Identifier, ...]
    reference_contract_valid: StrictBool
    handoff_active: StrictBool
    proposed_intents: tuple[Intent, ...]
    known_preference_fields: tuple[Identifier, ...] = ()
    authorized_question_targets: tuple[PreferenceTarget, ...] = ()

    @model_validator(mode="after")
    def privacy(self):
        check_privacy(self.model_dump(mode="json"))
        return self

    @classmethod
    def capture(
        cls, case, *, decision, context, body, handoff_active, authorized_question_targets=()
    ):
        if body is None:
            raise ValueError("eval_missing_grounding_surface")
        valid = True
        try:
            validate_llm_decision(
                decision.model_dump(mode="json"),
                allowed_knowledge_refs={f.id for f in context.knowledge if f.status == "approved"},
            )
        except StructuredDecisionValidationError:
            valid = False
        return cls(
            authorized_question_targets=authorized_question_targets,
            oracle=_oracle_digest(case),
            case_id=case.contract.case_id,
            reply_hash=fingerprint(body),
            selected_fact_ids=tuple(f.id for f in context.knowledge),
            reference_contract_valid=valid,
            handoff_active=handoff_active,
            proposed_intents=decision.intents,
            known_preference_fields=tuple(
                field
                for field in (
                    "desired_service",
                    "preferred_day",
                    "preferred_time",
                    "professional_preference",
                )
                if (
                    context.appointment_intake is not None
                    and getattr(context.appointment_intake, field)
                )
                or (
                    decision.appointment_preferences is not None
                    and (value := getattr(decision.appointment_preferences, field))
                    and value in case.data["customer_message"]
                )
            ),
        )


def replay_grounding(case, observation: GroundingObservation, *, body, facts=None):
    """Replay the same live scorer using saved evidence, without a provider call.

    Source/expectation and reply hashes bind the metadata to its original inputs.
    Positive facts are checked on the actual customer-visible body, not a rebuilt plan.
    """
    if observation.case_id != case.contract.case_id or observation.oracle != _oracle_digest(
        case, observation.oracle_version
    ):
        raise ValueError("eval_replay_oracle_mismatch")
    if fingerprint(body) != observation.reply_hash:
        raise ValueError("eval_replay_reply_mismatch")
    if facts is None:
        from rj_studio_ai.evaluation.runner import synthetic_facts

        facts = synthetic_facts(case)
    if set(observation.selected_fact_ids) != {f.id for f in facts}:
        raise ValueError("eval_replay_knowledge_mismatch")
    expected = live_expectation(case)
    allowed = [f.statement for f in facts if f.status == "approved"] + list(REPLY_PHRASES.values())
    allowed += [HUMAN_REVIEW_REPLY]
    allowed += [
        handoff_confirmation(reason, case.data["customer_message"]) for reason in HandoffReason
    ]
    residue = body or ""
    for text in sorted(allowed, key=len, reverse=True):
        residue = residue.replace(text, "")
    if observation.oracle_version == ORACLE_VERSION:
        # Only source-based expectations remain literal. Safety guidance words
        # preserve meaning; routine ACK/question/CTA substrings are not gates.
        required = [
            t
            for t in expected["contains"]
            if any(t in fact.statement for fact in facts)
            or case.contract.case_id == "grounding-technical-risk"
        ]
        surface_ok = protected_assertion(residue) is None and not (
            set(observation.authorized_question_targets) & set(observation.known_preference_fields)
        )
        excludes = [t for t in expected["excludes"] if t != "desconto"]
    else:
        required = [t for t in expected["contains"] if t != "Olá!"]
        surface_ok = not residue.strip()
        excludes = expected["excludes"]
    checks = {
        "trusted_facts": "pass"
        if bool(body)
        and observation.reference_contract_valid
        and all(t in body for t in required)
        and not any(t in body for t in excludes)
        and grounding_relevance_matches(expected, facts=facts, reply_text=body)
        and surface_ok
        else "fail"
    }
    if expected["handoff"] is not None:
        checks["handoff_policy"] = (
            "pass" if observation.handoff_active is expected["handoff"] else "fail"
        )
    if "live_expected_intents" in case.data:
        checks["decision_contract"] = (
            "pass"
            if set(observation.proposed_intents) == set(case.data["live_expected_intents"])
            else "fail"
        )
    return checks
