"""Explicitly authorized OpenAI-only live eval; synthetic SQLite and fake delivery only."""

import argparse
import json
import logging
import os
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Literal

import httpx
from dotenv import dotenv_values
from pydantic import model_validator

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.conversation_context import (
    ConversationContext,
    ConversationContextBuilder,
    ConversationContextLimits,
)
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.openai_live import LiveAttempt, OpenAIEvalGenerator, eval_prompt
from rj_studio_ai.evaluation.records import (
    Fingerprints,
    RecordModel,
    Sample,
    check_privacy,
    fingerprint,
    summarize,
)
from rj_studio_ai.evaluation.runner import prepare_context_case, synthetic_facts, synthetic_message
from rj_studio_ai.evaluation.suite import load_suite
from rj_studio_ai.grounding import finalize_reply
from rj_studio_ai.handoff import HandoffReason, handoff_confirmation
from rj_studio_ai.livia_persona import (
    HUMAN_REVIEW_REPLY,
    REPLY_PHRASES,
    LiviaPersona,
    PersonaValidationError,
)
from rj_studio_ai.llm_decision import decision_json_schema
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.providers.base import ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

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


class LiveRecord(RecordModel):
    schema_version: Literal[2] = 2
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


def _score(case, turn, decision, context, body, store, claim, context_checks):
    data = case.data
    if case.kind == "grounding":
        if decision is None:
            return {key: False for key in case.contract.checks}
        finalized = finalize_reply(
            decision, customer_message=turn["customer_message"], context=context
        )
        # Surface greetings belong to naturalness, not the critical factual oracle.
        contains = [text for text in data["expected"]["contains"] if text != "Olá!"]
        allowed = [fact.statement for fact in context.knowledge] + list(REPLY_PHRASES.values())
        allowed += [HUMAN_REVIEW_REPLY]
        allowed += [
            handoff_confirmation(reason, turn["customer_message"]) for reason in HandoffReason
        ]
        residue = body or ""
        for text in sorted(allowed, key=len, reverse=True):
            residue = residue.replace(text, "")
        return {
            "trusted_facts": bool(body)
            and all(t in finalized.reply_text for t in contains)
            and not any(t in (body or "") for t in data["expected"]["excludes"])
            and not residue.strip(),
            "handoff_policy": bool(store.list_active_handoffs()) is data["expected"]["handoff"],
        }
    if case.kind == "intent":
        return {
            "decision_contract": decision is not None
            and set(decision.intents) == set(data["expected_intents"])
        }
    if case.kind == "persona":
        passed = bool(body)
        try:
            LiviaPersona().validate_reply(turn["customer_message"], body or "")
        except PersonaValidationError:
            passed = False
        if "clarify" in data["checks"]:
            passed &= bool(body and "?" in body)
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
    bounded = (
        intake is None
        if expected.get("intake_absent")
        else (intake is not None and intake.clarification_count == expected["clarification_count"])
    )
    prohibited = (
        "agendei",
        "vaga confirmada",
        "vaga está reservada",
        "horário está confirmado",
        "temos horário às",
        "pode vir sexta",
    )
    return {
        "no_booking_claim": body is not None
        and expected["contains"] in body
        and not any(t in body.casefold() for t in prohibited),
        "handoff_policy": active is expected["handoff"],
        "bounded_intake": bounded,
    }


def _write(path, data):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())


def live_summary(samples, contracts, pricing):
    summary = summarize(samples, contracts).model_dump(mode="json")
    attempts = [a for s in samples for a in s.attempts]
    cost = sum(pricing.cost(a.usage) for a in attempts if a.usage is not None)
    known = all(a.usage is not None for a in attempts)
    completed = summary["completed_replies"]
    summary.update(
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
        if known
        else None,
        estimated_cost_usd=float(cost) if known else None,
        cost_per_1000_replies_usd=float(cost * 1000 / completed) if known and completed else None,
    )
    appointment_checks = [
        s.checks["no_booking_claim"] for s in samples if "no_booking_claim" in s.checks
    ]
    summary["appointment_safety"] = {
        "numerator": appointment_checks.count("pass"),
        "denominator": len(appointment_checks),
    }
    return summary


def _run_phase(suite, selections, phase, *, api_key, output, revision, ledger, client):
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
                context_checks, _, _ = prepare_context_case(case, store, directory)
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
                # Admission starts the measured E2E; setup/fixture seeding is outside it.
                started = perf_counter()
                claim = store.admit_generation(message)
                context = builder.build(
                    inbound_message_id=claim.inbound_message_id, current_body=message.body
                )
                generator = OpenAIEvalGenerator(
                    api_key=api_key, client=client, ledger=ledger, phase=phase
                )
                reply = MessageResponder(
                    store=store,
                    generator=generator,
                    context_builder=builder,
                    safe_failure_reply="Falha sintética",
                    completion_delivery_state=DeliveryState.PENDING,
                ).process_persisted(message)
                body = reply.body if reply else None
                outbound_started = perf_counter()
                if body:
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
                checks = _score(case, turn, decision, context, body, store, claim, context_checks)
                sample = LiveSample(
                    case_id=identifier,
                    repetition=repetition,
                    turn=number,
                    status=("completed" if generator.attempts else "observed")
                    if body
                    else "suppressed",
                    reply_hash=fingerprint(body) if body else None,
                    attempts=tuple(generator.attempts),
                    e2e_latency_ms=e2e_ms,
                    queue_latency_ms=0.0,
                    outbound_latency_ms=outbound_ms,
                    checks={k: "pass" if v else "fail" for k, v in checks.items()},
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
                critical = any(not checks[k] for k, v in case.contract.checks.items() if v.critical)
                if generator.stop_code or critical:
                    stop_code = generator.stop_code or "critical_failure"
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
            "reasoning_effort": "medium",
            "service_tier": "default",
            "max_output_tokens": 200,
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
        request_hashes=tuple(hashes),
    )
    _write(output / f"phase-{phase}.json", record.model_dump(mode="json"))
    return record, packet


def execute_live(suite, *, api_key, output: Path, revision: str, transport=None):
    output.mkdir(mode=0o700)
    pricing = LivePricing.load()
    ledger = BudgetLedger(output / "spend.jsonl", pricing)
    records, packet = [], []
    try:
        with httpx.Client(transport=transport, follow_redirects=False) as client:
            a, excerpts = _run_phase(
                suite,
                [(i, 1) for i in SMOKE_CASES],
                "A",
                api_key=api_key,
                output=output,
                revision=revision,
                ledger=ledger,
                client=client,
            )
            records.append(a)
            packet.extend(excerpts)
            if a.status == "completed":
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
                b, excerpts = _run_phase(
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
        report = {
            "phase_a_status": a.status,
            "phase_a_stop_code": a.stop_code,
            "phase_b_executed": len(records) > 1,
            "phase_b_status": records[1].status if len(records) > 1 else "not_executed",
            "summary": live_summary(samples, tuple(c.contract for c in suite.cases), pricing),
            "budget_upper_bound_usd": float(ledger.upper_bound_usd),
            "phase_a_cap_usd": 1,
            "global_cap_usd": 5,
            "latency_scope": "synthetic_persistence_to_fake_provider_acceptance",
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
            {"rubric": RUBRIC, "review_status": "pending", "items": packet},
        )
        text = "# Revisão humana\n\nAvalie cada dimensão de 1 a 5; sem nota automática.\n\n"
        text += "\n".join(f"- {dimension}" for dimension in RUBRIC) + "\n"
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
            load_suite(Path("docs/evals/V1")), api_key=key, output=args.output, revision=revision
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        parser.exit(1, "live_eval_stopped_inspect_private_evidence\n")


if __name__ == "__main__":
    main()
