"""Explicitly authorized OpenAI-only live eval; synthetic SQLite and fake delivery only."""

import argparse
import json
import logging
import math
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter
from typing import Literal

import httpx
from dotenv import dotenv_values
from pydantic import model_validator

from rj_studio_ai.application import MessageResponder, RetryableWebhookError
from rj_studio_ai.conversation_context import (
    ConversationContext,
    ConversationContextBuilder,
    ConversationContextLimits,
)
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.evaluation.behavioral import (
    expected_customer_preferences,
    score_appointment,
    score_persona,
)
from rj_studio_ai.evaluation.decision_trace import DecisionTrace, capture_finalizer
from rj_studio_ai.evaluation.latency import (
    RECONCILIATION_TOLERANCE_MS,
    LatencyBreakdown,
    LatencyRecorder,
    observe_store,
    summarize_latency,
)
from rj_studio_ai.evaluation.live_billing import LIVE_MAX_OUTPUT_TOKENS, BudgetLedger, LivePricing
from rj_studio_ai.evaluation.openai_live import (
    LIVE_CONNECT_TIMEOUT_SECONDS,
    LIVE_INPUT_COUNT_TIMEOUT_SECONDS,
    LiveAttempt,
    OpenAIEvalGenerator,
    eval_prompt,
)
from rj_studio_ai.evaluation.oracle import (
    ORACLE_VERSION,
    PHASE_ONE_ORACLE_VERSION,
    GroundingObservation,
    execution_category,
    replay_grounding,
    requires_general_clarification,
)
from rj_studio_ai.evaluation.records import (
    PRODUCT_E2E_LATENCY_LIMIT_MS,
    CaseContract,
    CheckContract,
    Fingerprints,
    RecordModel,
    Sample,
    check_privacy,
    fingerprint,
    summarize,
)
from rj_studio_ai.evaluation.runner import seed_context_history, synthetic_facts, synthetic_message
from rj_studio_ai.evaluation.suite import load_suite
from rj_studio_ai.handoff import handoff_confirmation, safe_handoff_reason
from rj_studio_ai.llm_decision import decision_json_schema, uses_agentic_surface
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

LIVE_OBSERVATION_DEADLINE_SECONDS = 30.0

SMOKE_CASES = (
    "grounding-divergent-price",
    "grounding-unknown-price",
    "grounding-false-customer-fact-and-injection",
    "grounding-unauthorized-discount",
    "grounding-technical-risk",
    "grounding-explicit-human-request",
    "appointment-model-availability-promise",
    "appointment-cancellation",
    "persona-incomplete-context",
    "grounding-multiple-facts",
)
COMMERCIAL_RETEST_CASES = (SMOKE_CASES[0], SMOKE_CASES[1], SMOKE_CASES[3])
INITIATIVE_RETEST_CASES = (*COMMERCIAL_RETEST_CASES, SMOKE_CASES[4])

RUBRIC = (
    "naturalidade de WhatsApp",
    "clareza",
    "concisão",
    "persona Lívia",
    "excesso de formalidade",
    "repetição",
    "utilidade comercial",
)


class LiveSample(Sample):
    attempts: tuple[LiveAttempt, ...]
    reply_origin: Literal["model", "system_safe_fallback", "none"]
    decision_trace: DecisionTrace | None = None
    latency_breakdown: LatencyBreakdown | None = None
    grounding_observation: GroundingObservation | None = None
    execution_kind: Literal[
        "live_generation",
        "handoff_suppression",
        "delivery_barrier",
        "preflight_failure",
        "deterministic_adversarial",
    ]

    @model_validator(mode="after")
    def matching_reply_origin(self):
        if self.grounding_observation is not None and (
            self.grounding_observation.case_id != self.case_id
            or self.grounding_observation.reply_hash != self.reply_hash
        ):
            raise ValueError("live_grounding_observation_mismatch")
        if self.reply_origin == "model" and (
            self.status != "completed"
            or not self.attempts
            or self.attempts[-1].outcome != "success"
        ):
            raise ValueError("live_invalid_model_reply")
        if (self.reply_origin == "none") != (self.reply_hash is None):
            raise ValueError("live_invalid_reply_origin")
        if self.latency_breakdown is not None:
            observed = self.latency_breakdown.observed_eval_e2e_ms
            if (
                observed is None
                or self.e2e_latency_ms is None
                or not math.isclose(
                    observed, self.e2e_latency_ms, abs_tol=RECONCILIATION_TOLERANCE_MS, rel_tol=0
                )
            ):
                raise ValueError("live_latency_total_mismatch")
            model = self.latency_breakdown.model_request_ms
            if self.attempts and (
                model is None
                or not math.isclose(
                    model,
                    sum(a.latency_ms for a in self.attempts),
                    abs_tol=RECONCILIATION_TOLERANCE_MS,
                    rel_tol=0,
                )
            ):
                raise ValueError("live_model_latency_mismatch")
        return self


class LiveRecord(RecordModel):
    schema_version: Literal[3, 4, 5, 6, 7, 8, 9] = 9
    created_at: datetime
    revision: str
    phase: Literal["A", "B"]
    status: Literal["completed", "blocked", "budget_exhausted"]
    stop_code: str | None
    configuration: dict
    fingerprints: Fingerprints
    pricing: LivePricing
    plan: tuple[tuple[str, int, int], ...]
    samples: tuple[LiveSample, ...]
    contracts: tuple[CaseContract, ...]
    request_hashes: tuple[str, ...]
    latency_scope: Literal["synthetic_persistence_to_fake_provider_acceptance"] = (
        "synthetic_persistence_to_fake_provider_acceptance"
    )
    naturalness_status: Literal["pending_human_review"] = "pending_human_review"
    cross_provider_comparison: Literal["deferred_by_product_owner"] = "deferred_by_product_owner"

    @model_validator(mode="after")
    def validate_execution(self):
        check_privacy(self.model_dump(mode="json", exclude={"request_hashes"}))
        if self.created_at.tzinfo is None:
            raise ValueError("live_missing_timezone")
        expected_oracle = PHASE_ONE_ORACLE_VERSION if self.schema_version == 8 else ORACLE_VERSION
        if self.schema_version >= 8 and self.configuration.get("oracle_version") != expected_oracle:
            raise ValueError("live_missing_oracle_version")
        observed = [(s.case_id, s.repetition, s.turn) for s in self.samples]
        if len(set(self.plan)) != len(self.plan) or len(set(observed)) != len(observed):
            raise ValueError("live_duplicate_sample")
        if not set(observed).issubset(set(self.plan)) or (
            self.status == "completed" and set(observed) != set(self.plan)
        ):
            raise ValueError("live_missing_or_extra_sample")
        if len(self.request_hashes) != sum(len(s.attempts) for s in self.samples):
            raise ValueError("live_unaccounted_attempt")
        if any(
            len(h) != 64 or any(c not in "0123456789abcdef" for c in h) for h in self.request_hashes
        ):
            raise ValueError("live_invalid_digest")
        for sample in self.samples:
            if self.schema_version >= 4 and sample.decision_trace is None:
                raise ValueError("live_missing_decision_trace")
            if self.schema_version >= 5 and any(
                attempt.response_diagnostics is None for attempt in sample.attempts
            ):
                raise ValueError("live_missing_response_diagnostics")
            if self.schema_version >= 6 and sample.latency_breakdown is None:
                raise ValueError("live_missing_latency_breakdown")
            if (
                self.schema_version >= 7
                and "trusted_facts" in sample.checks
                and sample.reply_origin == "model"
                and sample.grounding_observation is None
            ):
                raise ValueError("live_missing_grounding_observation")
            contract = next(c for c in self.contracts if c.case_id == sample.case_id)
            if sample.checks.keys() != contract.checks.keys():
                raise ValueError("live_missing_check")
            if sample.status == "completed" and not sample.attempts:
                raise ValueError("live_missing_generation_evidence")
            if sample.attempts and (
                sample.e2e_latency_ms is None
                or sample.e2e_latency_ms < sum(a.latency_ms for a in sample.attempts)
            ):
                raise ValueError("live_attempt_latency_omitted")
        return self


class _SelectedKnowledgeContext:
    """Use the fixture-selected facts, never real runtime Knowledge or expected decisions."""

    def __init__(self, store, repository, facts, incomplete=False):
        self.builder = ConversationContextBuilder(
            store=store, salon_knowledge=repository, limits=ConversationContextLimits()
        )
        self.facts = facts
        self.incomplete = incomplete

    def build(self, **kwargs):
        context = self.builder.build(**kwargs)
        return replace(
            context,
            knowledge=self.facts,
            history_may_be_incomplete=context.history_may_be_incomplete or self.incomplete,
        )


def _episode_action(turn, store):
    if turn.get("action") == "release":
        active = store.list_active_handoffs()
        if active:
            store.release_handoff(
                conversation_id=active[0].conversation_id, owner_token=active[0].owner_token
            )


def _score(
    case, turn, decision, context, body, store, claim, context_checks, *, decision_trace=None
):
    data = case.data
    if case.kind == "grounding":
        if decision is None:
            return {key: False for key in case.contract.checks}
        observation = GroundingObservation.capture(
            case,
            decision=decision,
            context=context,
            body=body,
            handoff_active=bool(store.list_active_handoffs()),
            actionable_information_targets=decision_trace.actionable_information_targets
            if decision_trace
            else (),
        )
        return {
            k: v == "pass"
            for k, v in replay_grounding(
                case, observation, body=body, facts=context.knowledge
            ).items()
        }
    if case.kind == "intent":
        return {
            "decision_contract": decision is not None
            and set(decision.intents) == set(data["expected_intents"])
        }
    if case.kind == "persona":
        passed = score_persona(
            customer_message=turn["customer_message"],
            body=body,
            clarify="clarify" in data["checks"],
        )
        return {"persona_surface": passed}
    if case.kind == "context":
        return context_checks
    active = bool(store.list_active_handoffs())
    expected = turn["expected"]
    if case.kind == "handoff":
        return {
            "durable_handoff": active is expected["active"],
            "suppression": (body is None) is expected["suppressed"],
        }
    intake = store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)
    episodes = store.list_active_handoffs()
    confirmation = (
        handoff_confirmation(safe_handoff_reason(episodes[0].reason_code), turn["customer_message"])
        if episodes
        else ""
    )
    return score_appointment(
        expected,
        body=body,
        intake=intake,
        prior=context.appointment_intake,
        active=active,
        trusted_confirmation=confirmation,
        authorized_targets=(
            decision_trace.authorized_appointment_targets
            if decision_trace is not None
            and decision is not None
            and uses_agentic_surface(decision)
            else None
        ),
        expected_preferences=expected_customer_preferences(turn, context.appointment_intake),
        handoff_reason=episodes[0].reason_code if episodes else None,
    )


def _write(path, data):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())


def live_summary(samples, contracts, pricing):
    run_count = len({s.repetition for s in samples}) or 1
    summary = summarize(samples, contracts, run_count=run_count).model_dump(mode="json")
    provider_samples = [s for s in samples if s.attempts or s.execution_kind == "preflight_failure"]
    if provider_samples:
        quality = summarize(provider_samples, contracts, run_count=run_count).model_dump(
            mode="json"
        )
        summary["metrics"] = quality["metrics"]
        summary["critical_failures"] = quality["critical_failures"]
    else:
        summary["metrics"] = {
            c.metric: {"numerator": 0, "denominator": 0}
            for contract in contracts
            for c in contract.checks.values()
        }
        summary["critical_failures"] = {"numerator": 0, "denominator": 0}
    summary["deterministic_guard_turns"] = sum(
        s.execution_kind in {"delivery_barrier", "handoff_suppression", "deterministic_adversarial"}
        for s in samples
    )
    summary["critical_not_evaluable"] = sum(
        s.checks[key] == "not_run"
        for s in provider_samples
        for contract in contracts
        if contract.case_id == s.case_id
        for key, check in contract.checks.items()
        if check.critical
    )
    # Unavailable output is a generation failure, not an evaluated quality failure.
    for metric, ratio in summary["metrics"].items():
        unevaluable = sum(
            s.checks[key] == "not_run"
            for s in provider_samples
            for contract in contracts
            if contract.case_id == s.case_id
            for key, check in contract.checks.items()
            if check.metric == metric
        )
        ratio["denominator"] -= unevaluable
    persona_checks = [s.checks["persona_surface"] for s in samples if "persona_surface" in s.checks]
    summary["persona"] = {
        "evaluable": persona_checks.count("pass") + persona_checks.count("fail"),
        "pass": persona_checks.count("pass"),
        "fail": persona_checks.count("fail"),
        "not_evaluable": persona_checks.count("not_run"),
    }
    attempts = [a for s in samples for a in s.attempts]
    cost = sum(pricing.cost(a.usage) for a in attempts if a.usage is not None)
    known = all(a.usage is not None and a.pricing_verified for a in attempts)
    completed = sum(s.reply_origin == "model" for s in samples)
    summary.update(
        completed_logical_replies=sum(s.reply_hash is not None for s in samples),
        completed_replies=completed,
        completed_model_replies=completed,
        system_safe_fallbacks=sum(s.reply_origin == "system_safe_fallback" for s in samples),
        generation_failures=sum(
            s.execution_kind == "preflight_failure"
            or bool(s.attempts and s.attempts[-1].outcome == "failure")
            for s in samples
        ),
        cost_denominator="completed_model_replies",
        live_calls=len(attempts),
        retries=sum(a.number > 1 for a in attempts),
        paid_failures=sum(
            a.outcome == "failure"
            and a.usage is not None
            and a.usage.input_tokens + a.usage.output_tokens > 0
            for a in attempts
        ),
        cached_input_tokens=sum(a.usage.cached_tokens for a in attempts if a.usage is not None)
        if known
        else None,
        cache_write_tokens=sum(a.usage.cache_write_tokens for a in attempts if a.usage is not None)
        if known
        else None,
        reasoning_tokens=sum(a.usage.reasoning_tokens for a in attempts if a.usage is not None)
        if known and all(a.usage.reasoning_tokens is not None for a in attempts)
        else None,
        estimated_cost_usd=float(cost) if known else None,
        cost_per_1000_replies_usd=float(cost * 1000 / completed) if known and completed else None,
    )
    appointment_checks = [
        s.checks["no_booking_claim"]
        for s in provider_samples
        if "no_booking_claim" in s.checks and s.checks["no_booking_claim"] != "not_run"
    ]
    summary["appointment_safety"] = {
        "numerator": appointment_checks.count("pass"),
        "denominator": len(appointment_checks),
    }
    summary["latency_breakdown"] = summarize_latency(samples)
    return summary


def _live_contracts(suite):
    cases = []
    for case in suite.cases:
        data = dict(case.data)
        if case.kind == "grounding":
            data["expected"] = data.pop("live_expected", data["expected"])
            # Only the deterministic runner injects a fixture proposal.
            data.pop("proposal", None)
        if case.kind in {"appointment", "handoff"}:
            data["turns"] = [
                {
                    **{
                        k: v
                        for k, v in turn.items()
                        if k not in {"preferences", "adversarial_reply_text"}
                    },
                    # Observer evidence only; never supplied to the generator.
                    "customer_preference_expectations": turn.get(
                        "customer_preference_expectations", turn.get("preferences", {})
                    ),
                }
                for turn in data["turns"]
            ]
        checks = dict(case.contract.checks)
        if case.kind == "grounding" and data["expected"]["handoff"] is None:
            checks.pop("handoff_policy", None)
        if "live_expected_intents" in data:
            checks["decision_contract"] = CheckContract(metric="intent")
        if requires_general_clarification(case):
            checks["general_clarification"] = CheckContract(metric="commercial")
        cases.append(
            replace(
                case,
                data=data,
                contract=CaseContract(**{**case.contract.model_dump(), "checks": checks}),
            )
        )
    return replace(
        suite,
        cases=tuple(cases),
    )


def run_live_phase(
    suite,
    selections,
    phase,
    *,
    api_key,
    output,
    revision,
    ledger,
    client,
    stop_on_any_failure=False,
    reasoning_effort="medium",
):
    suite = _live_contracts(suite)
    samples, packet, hashes = [], [], []
    by_id = {c.contract.case_id: c for c in suite.cases}
    plan = tuple(
        (identifier, rep, number)
        for identifier, rep in selections
        for number in range(1, by_id[identifier].contract.turns + 1)
    )
    stop_code = None
    for identifier, repetition in selections:
        case = by_id[identifier]
        with TemporaryDirectory(prefix="rj-live-eval-") as directory:
            directory = Path(directory)
            database = directory / "synthetic.db"
            store = SqliteConversationStore(database)
            store.initialize()
            knowledge_path = directory / "synthetic.yaml"
            knowledge_path.write_text("version: 1\nfacts: []\n")
            repository = SalonKnowledgeRepository(knowledge_path)
            repository.load()
            context_checks = None
            if case.kind == "context":
                seed_context_history(case, store)
            facts = synthetic_facts(case) if case.kind == "grounding" else ()
            builder = _SelectedKnowledgeContext(
                store, repository, facts, identifier == "persona-incomplete-context"
            )
            for number, turn in enumerate(case.data.get("turns", [case.data]), 1):
                if turn.get("action") == "restart":
                    store = SqliteConversationStore(database)
                    builder = _SelectedKnowledgeContext(store, repository, facts)
                _episode_action(turn, store)
                customer_body = turn.get("customer_message", "Outra dúvida")
                message = synthetic_message(f"live-{number}", customer_body)
                timing = LatencyRecorder(clock=perf_counter)
                # Admission starts the measured E2E; setup/fixture seeding is outside it.
                started = perf_counter()
                observation_deadline = ExecutionDeadline.start(
                    clock=monotonic, total_seconds=LIVE_OBSERVATION_DEADLINE_SECONDS
                )
                with observe_store(store, timing):
                    claim = store.admit_generation(message)
                with timing.measure("eval_bookkeeping_ms"):
                    context = builder.build(
                        inbound_message_id=claim.inbound_message_id, current_body=message.body
                    )
                if case.kind == "context":
                    expected = case.data["expected"]
                    context_checks = {
                        "context_bounds": len(context.history) == expected["history_count"]
                        and context.history_may_be_incomplete is expected["incomplete"]
                    }
                generator = OpenAIEvalGenerator(
                    api_key=api_key,
                    client=client,
                    ledger=ledger,
                    phase=phase,
                    timing=timing,
                    reasoning_effort=reasoning_effort,
                )
                with timing.measure("eval_bookkeeping_ms"):
                    generator.trace_capture.propose(None, context)
                with (
                    capture_finalizer(generator.trace_capture, timing=timing),
                    observe_store(store, timing),
                ):
                    try:
                        reply = (
                            None
                            if execution_category(case) == "STRUCTURAL_CONTRACT"
                            else MessageResponder(
                                store=store,
                                generator=generator,
                                context_builder=builder,
                                safe_failure_reply="Falha sintética",
                                completion_delivery_state=DeliveryState.PENDING,
                            ).process_persisted(message, execution_deadline=observation_deadline)
                        )
                    except RetryableWebhookError:
                        # A late failure may no longer own the SQLite claim. Keep
                        # observed billing evidence without inventing a persisted reply.
                        if generator.stop_code is None:
                            if observation_deadline.work_budget() > 0:
                                raise
                            generator.stop_code = "live_observation_timeout"
                        reply = None
                body = reply.body if reply else None
                outbound_started = perf_counter()
                if body:
                    with timing.measure("fake_outbound_ms"):
                        sender = DeterministicFakeOutboundSender(
                            outcomes=[ProviderAcceptance(provider_message_id=f"fake-{number}")]
                        )
                        accepted = OutboundDeliveryRunner(
                            store=store, sender=sender, timeout_seconds=1
                        ).run_once()
                        if accepted is None or accepted.state is not DeliveryState.ACCEPTED:
                            raise ValueError("eval_fake_acceptance_missing")
                outbound_ms = (perf_counter() - outbound_started) * 1000
                e2e_ms = (perf_counter() - started) * 1000
                decision = generator.decisions[-1] if generator.decisions else None
                safe_fallback = bool(body and (decision is None or generator.stop_code is not None))
                handoffs = store.list_active_handoffs()
                observation = None
                if generator.stop_code:
                    checks = {key: "not_run" for key in case.contract.checks}
                elif case.kind == "grounding" and decision is not None:
                    observation = GroundingObservation.capture(
                        case,
                        decision=decision,
                        context=context,
                        body=body,
                        handoff_active=bool(handoffs),
                        authorized_question_targets=generator.trace_capture.trace.authorized_appointment_targets,
                        actionable_information_targets=generator.trace_capture.trace.actionable_information_targets,
                    )
                    checks = replay_grounding(case, observation, body=body, facts=context.knowledge)
                else:
                    checks = {
                        key: "pass" if passed else "fail"
                        for key, passed in _score(
                            case,
                            turn,
                            decision,
                            context,
                            body,
                            store,
                            claim,
                            context_checks,
                            decision_trace=generator.trace_capture.trace,
                        ).items()
                    }
                sample = LiveSample(
                    case_id=identifier,
                    repetition=repetition,
                    turn=number,
                    status=("completed" if generator.attempts else "observed")
                    if body
                    else (
                        "failed"
                        if generator.stop_code
                        else "observed"
                        if case.kind == "context"
                        else "suppressed"
                    ),
                    reply_hash=fingerprint(body) if body else None,
                    grounding_observation=observation,
                    decision_trace=generator.trace_capture.finish(
                        body,
                        safe_fallback=safe_fallback,
                        persisted_handoff_reason=handoffs[0].reason_code if handoffs else None,
                    ),
                    reply_origin=(
                        "model"
                        if decision is not None and generator.stop_code is None
                        else "system_safe_fallback"
                    )
                    if body
                    else "none",
                    attempts=tuple(generator.attempts),
                    latency_breakdown=timing.finish(e2e_ms),
                    e2e_latency_ms=e2e_ms,
                    queue_latency_ms=0.0,
                    outbound_latency_ms=outbound_ms,
                    checks=checks,
                    execution_kind="live_generation"
                    if generator.attempts
                    else (
                        "preflight_failure"
                        if generator.stop_code
                        else (
                            "deterministic_adversarial"
                            if case.kind == "context"
                            else "handoff_suppression"
                        )
                    ),
                )
                samples.append(sample)
                hashes.extend(generator.request_hashes)
                check_privacy({"scenario": customer_body, "response": body})
                if body and decision is not None and generator.stop_code is None:
                    packet.append({"scenario": customer_body, "response": body})
                _write(
                    output / f"{phase}-{len(samples):03}-sample.json",
                    sample.model_dump(mode="json"),
                )
                critical = any(
                    checks[k] != "pass" for k, v in case.contract.checks.items() if v.critical
                )
                product_failure = stop_on_any_failure and any(v != "pass" for v in checks.values())
                if generator.stop_code or critical or product_failure:
                    stop_code = generator.stop_code or (
                        "critical_failure" if critical else "behavioral_failure"
                    )
                    break
            if stop_code:
                break
    record = LiveRecord(
        created_at=datetime.now(UTC),
        revision=revision,
        phase=phase,
        status=("budget_exhausted" if stop_code == "budget_exhausted" else "blocked")
        if stop_code
        else "completed",
        stop_code=stop_code,
        configuration={
            "provider": "openai",
            "model": "gpt-6.1-sol",
            "reasoning_effort": reasoning_effort,
            "service_tier": "default",
            "max_output_tokens": LIVE_MAX_OUTPUT_TOKENS,
            "observation_deadline_seconds": LIVE_OBSERVATION_DEADLINE_SECONDS,
            "finalization_margin_seconds": ExecutionDeadline.DEFAULT_FINALIZATION_MARGIN_SECONDS,
            "http_connect_timeout_seconds": LIVE_CONNECT_TIMEOUT_SECONDS,
            "input_count_timeout_seconds": LIVE_INPUT_COUNT_TIMEOUT_SECONDS,
            "model_latency_scope": "responses_http_request",
            "oracle_version": ORACLE_VERSION,
            "context_max_messages": 12,
            "context_token_budget": 4000,
            "repetitions_by_case": selections,
        },
        fingerprints=Fingerprints(
            suite=suite.digest,
            knowledge=suite.knowledge_digest,
            prompt=fingerprint([eval_prompt(ConversationContext((), ())), decision_json_schema()]),
        ),
        pricing=ledger.pricing,
        plan=plan,
        samples=tuple(samples),
        contracts=tuple(
            case.contract
            for case in suite.cases
            if case.contract.case_id in {identifier for identifier, _ in selections}
        ),
        request_hashes=tuple(hashes),
    )
    _write(output / f"phase-{phase}.json", record.model_dump(mode="json"))
    return record, packet


def _measured_latency_gate(summary):
    p95 = summary["billable_e2e_p95_ms"]
    if p95 is None or summary["unknown_billing_attempts"]:
        return "pending_evidence"
    return "pass" if p95 <= PRODUCT_E2E_LATENCY_LIMIT_MS else "fail"


def execute_live(
    suite,
    *,
    api_key,
    output: Path,
    revision: str,
    transport=None,
    case_id=None,
    smoke_only=False,
    commercial_only=False,
    initiative_only=False,
    phase_b_authorized=False,
):
    suite = _live_contracts(suite)
    if sum((case_id is not None, smoke_only, commercial_only, initiative_only)) > 1:
        raise ValueError("live_conflicting_execution_scope")
    if case_id is not None and case_id not in {c.contract.case_id for c in suite.cases}:
        raise ValueError("live_unknown_case")
    output.mkdir(mode=0o700)
    pricing = LivePricing.load()
    phase_a_cap = (
        Decimal("0.20")
        if case_id is not None
        else Decimal("0.40")
        if initiative_only
        else Decimal("0.30")
        if commercial_only
        else Decimal("1")
    )
    ledger = BudgetLedger(
        output / "spend.jsonl",
        pricing,
        phase_a_cap=phase_a_cap,
        global_cap=phase_a_cap
        if case_id is not None or commercial_only or initiative_only or smoke_only
        else Decimal("5"),
    )
    records, packet = [], []
    try:
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            a, excerpts = run_live_phase(
                suite,
                [(case_id, 1)]
                if case_id is not None
                else [(i, 1) for i in INITIATIVE_RETEST_CASES]
                if initiative_only
                else [(i, 1) for i in COMMERCIAL_RETEST_CASES]
                if commercial_only
                else [(i, 1) for i in SMOKE_CASES],
                "A",
                api_key=api_key,
                output=output,
                revision=revision,
                ledger=ledger,
                client=client,
                stop_on_any_failure=commercial_only or initiative_only,
            )
            records.append(a)
            packet.extend(excerpts)
            a_summary = live_summary(a.samples, a.contracts, pricing)
            if (
                a.status == "completed"
                and _measured_latency_gate(a_summary) == "pass"
                and case_id is None
                and not smoke_only
                and not commercial_only
                and not initiative_only
                and phase_b_authorized
            ):
                repeated = {
                    c.contract.case_id
                    for c in suite.cases
                    if c.kind in {"grounding", "appointment", "handoff", "persona"}
                }
                selections = [(c.contract.case_id, 1) for c in suite.cases]
                # Smoke is the first run of selected cases. Reach at most three runs total.
                selections += [
                    (c.contract.case_id, rep)
                    for rep in (2, 3)
                    for c in suite.cases
                    if c.contract.case_id in repeated
                    and (rep == 2 or c.contract.case_id not in SMOKE_CASES)
                ]
                b, excerpts = run_live_phase(
                    suite,
                    selections,
                    "B",
                    api_key=api_key,
                    output=output,
                    revision=revision,
                    ledger=ledger,
                    client=client,
                )
                records.append(b)
                packet.extend(excerpts)
        samples = [s for record in records for s in record.samples]
        summary = live_summary(samples, tuple(c.contract for c in suite.cases), pricing)
        report = {
            "execution_scope": "single_case_diagnostic"
            if case_id is not None
            else "initiative_retest"
            if initiative_only
            else "commercial_retest"
            if commercial_only
            else "smoke_only"
            if smoke_only
            else "smoke_and_suite",
            "phase_a_status": a.status,
            "phase_a_stop_code": a.stop_code,
            "phase_b_executed": len(records) > 1,
            "phase_b_status": records[1].status if len(records) > 1 else "not_executed",
            "summary": summary,
            "phase_summaries": {
                phase: live_summary(record.samples, record.contracts, pricing) if record else None
                for phase, record in (("A", a), ("B", records[1] if len(records) > 1 else None))
            },
            "budget_upper_bound_usd": float(ledger.upper_bound_usd),
            "phase_a_cap_usd": float(ledger.phase_a_cap),
            "global_cap_usd": float(ledger.global_cap),
            "latency_scope": "synthetic_persistence_to_fake_provider_acceptance",
            "latency_threshold_ms": PRODUCT_E2E_LATENCY_LIMIT_MS,
            "measured_latency_gate": _measured_latency_gate(summary),
            "operational_latency_gate": "pending_real_provider_evidence",
            "cross_provider_comparison": "deferred_by_product_owner",
            "naturalness_status": "pending_human_review",
            "ticket_status": "in-progress",
            "planned_turns": sum(len(r.plan) for r in records),
            "executed_turns": len(samples),
            "unexecuted_turns": sum(len(r.plan) - len(r.samples) for r in records),
        }
        check_privacy(report)
        _write(output / "report.json", report)
        _write(
            output / "human-review.json",
            {"review_format": "qualitative", "review_status": "pending", "items": packet},
        )
        text = "# Revisão humana qualitativa\n\nSem notas automáticas ou numéricas.\n\n"
        text += (
            "- Parece uma atendente competente?\n- Parece interessada em ajudar?\n"
            "- Conduz a conversa quando existe oportunidade?\n- Sabe quando NÃO conduzir?\n"
            "- É comercial sem ser insistente?\n- Continua autônoma?\n"
            "- Fez algo factualmente ou operacionalmente errado?\n"
        )
        for index, item in enumerate(packet, 1):
            text += f"\n## Caso {index}\n\nCenário: {item['scenario']}\n\n"
            text += f"Resposta: {item['response'] or 'Sem resposta automática'}\n"
        with (output / "human-review.md").open("x", encoding="utf-8") as review:
            os.chmod(output / "human-review.md", 0o600)
            review.write(text)
        return report
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description="Authorized OpenAI-only synthetic live eval")
    parser.add_argument("--allow-paid", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--case", help="One synthetic case once; US$0.20 cap, never starts B")
    scope.add_argument("--smoke-only", action="store_true", help="Ten-case smoke; US$1 cap, no B")
    scope.add_argument(
        "--commercial-only", action="store_true", help="Three-case retest; shared US$0.30 cap, no B"
    )
    scope.add_argument(
        "--initiative-only", action="store_true", help="Four-case retest; shared US$0.40 cap, no B"
    )
    args = parser.parse_args()
    logging.getLogger("dotenv.main").disabled = True
    key = os.environ.get("OPENAI_API_KEY") or dotenv_values(".env").get("OPENAI_API_KEY")
    if not key:
        parser.exit(1, "OPENAI_API_KEY_missing\n")
    try:
        with httpx.Client(follow_redirects=False) as client:
            lookup = client.get(
                "https://api.openai.com/v1/models/gpt-6.1-sol",
                headers={"Authorization": "Bearer " + key},
                timeout=20,
            )
            if lookup.status_code != 200 or lookup.json().get("id") != "gpt-6.1-sol":
                parser.exit(1, "live_model_preflight_failed\n")
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        report = execute_live(
            load_suite(Path("docs/evals/V1")),
            api_key=key,
            output=args.output,
            revision=revision,
            case_id=args.case,
            smoke_only=args.smoke_only,
            commercial_only=args.commercial_only,
            initiative_only=args.initiative_only,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        parser.exit(1, "live_eval_stopped_inspect_private_evidence\n")


if __name__ == "__main__":
    main()
