"""Deterministic proposal → real policy/persistence seams. No provider factory or settings."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.conversation_context import (
    ConversationContext,
    ConversationContextBuilder,
    ConversationContextLimits,
)
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.records import (
    Attempt,
    Fingerprints,
    ModelConfiguration,
    RunRecord,
    Sample,
    fingerprint,
    summarize,
)
from rj_studio_ai.evaluation.suite import (
    EvalCase,
    EvalSuite,
    fixture_decision,
    grounding_relevance_matches,
)
from rj_studio_ai.generation import GeneratedReply
from rj_studio_ai.grounding import finalize_reply
from rj_studio_ai.livia_persona import (
    HUMAN_REVIEW_REPLY,
    REPLY_PHRASES,
    LiviaPersona,
    PersonaValidationError,
    reply_plan_instructions,
)
from rj_studio_ai.llm_decision import MAX_OUTPUT_TOKENS, LLMDecision
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.salon_knowledge import SalonKnowledgeFact, SalonKnowledgeRepository


def synthetic_facts(case: EvalCase):
    return tuple(
        SalonKnowledgeFact.model_validate(
            {
                "id": identifier,
                "topic": "corte",
                "category": "price",
                "status": "approved",
                "fact_type": "operational_commercial",
                "source": "synthetic fixture",
                "reviewed_at": "2026-10-02",
                "approved_by": "synthetic-operator",
                **fields,
            }
        )
        for identifier, fields in case.facts.items()
        if identifier in case.data["selected_facts"]
    )


class _FixtureGenerator:
    def __init__(self, decision):
        self.decision = decision
        self.latencies = []

    def is_configured(self):
        return True

    def generate(self, message, *, context, remaining_budget):
        started = perf_counter()
        result = GeneratedReply(decision=self.decision)
        self.latencies.append((perf_counter() - started) * 1000)
        return result


def synthetic_message(identifier, body):
    return InboundMessage("eval", identifier, "synthetic-customer", "synthetic-channel", body)


def seed_context_history(case, store):
    now = datetime.now(UTC)
    scenario = case.data["scenario"]
    count = 10 if scenario == "bounded" else 1
    prior_time = now - timedelta(days=31) if scenario == "expired" else now
    for number in range(count):
        claim = store.claim_generation(
            synthetic_message(f"prior-{number}", "Dúvida sintética"), now=prior_time
        )
        store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Resposta sintética",
            delivery_state=DeliveryState.PENDING
            if scenario == "pending"
            else DeliveryState.ACCEPTED_LEGACY,
            now=prior_time,
        )
    return now


def prepare_context_case(case, store, directory):
    now = seed_context_history(case, store)
    current = store.admit_generation(synthetic_message("current", "Outra dúvida"), now=now)
    knowledge_path = directory / "synthetic-knowledge.yaml"
    knowledge_path.write_text("version: 1\nfacts: []\n")
    knowledge = SalonKnowledgeRepository(knowledge_path)
    knowledge.load()
    context = ConversationContextBuilder(
        store=store,
        salon_knowledge=knowledge,
        limits=ConversationContextLimits(),
    ).build(inbound_message_id=current.inbound_message_id, current_body=current.inbound_body)
    expected = case.data["expected"]
    passed = (
        len(context.history) == expected["history_count"]
        and context.history_may_be_incomplete is expected["incomplete"]
    )
    return {"context_bounds": passed}, None, []


def _single_case(case):
    data = case.data
    started = perf_counter()
    if case.kind == "grounding":
        decision = fixture_decision(reply_parts=[{"kind": "phrase", "phrase": "information"}])
        decision = LLMDecision.model_validate({**decision.model_dump(), **data["proposal"]})
        result = finalize_reply(
            decision,
            customer_message=data["customer_message"],
            context=ConversationContext(history=(), knowledge=synthetic_facts(case)),
        )
        residue = result.reply_text
        approved_texts = [fact.statement for fact in synthetic_facts(case)]
        authorized_phrases = [*REPLY_PHRASES.values(), HUMAN_REVIEW_REPLY]
        for text in sorted([*approved_texts, *authorized_phrases], key=len, reverse=True):
            residue = residue.replace(text, "")
        checks = {
            "trusted_facts": all(text in result.reply_text for text in data["expected"]["contains"])
            and not any(text in result.reply_text for text in data["expected"]["excludes"])
            and grounding_relevance_matches(
                data["expected"], facts=synthetic_facts(case), reply_text=result.reply_text
            )
            and not residue.strip(),
        }
        if data["expected"]["handoff"] is not None:
            checks["handoff_policy"] = result.handoff is data["expected"]["handoff"]
    elif case.kind == "intent":
        # Oracle proposal tests the multi-intent schema, not model detection quality.
        result = fixture_decision(intents=data["expected_intents"])
        checks = {"decision_contract": list(result.intents) == data["expected_intents"]}
    else:
        phrase = "clarification" if "clarify" in data["checks"] else "detail_question"
        result = finalize_reply(
            fixture_decision(reply_parts=[{"kind": "phrase", "phrase": phrase}]),
            customer_message=data["customer_message"],
            context=ConversationContext(history=(), knowledge=()),
        )
        try:
            LiviaPersona().validate_reply(data["customer_message"], result.reply_text)
            passed = True
        except PersonaValidationError:
            passed = False
        checks = {"persona_surface": passed}
    return checks, result.reply_text, [(perf_counter() - started) * 1000]


def _episode_turn(case, turn, number, store, database_path):
    if turn.get("action") == "restart":
        store = SqliteConversationStore(database_path)
    elif turn.get("action") == "release":
        active = store.list_active_handoffs()
        if active:
            store.release_handoff(
                conversation_id=active[0].conversation_id, owner_token=active[0].owner_token
            )
    decision = fixture_decision(
        intents=turn.get(
            "expected_intents",
            ["appointment_interest"] if case.kind == "appointment" else ["greeting"],
        ),
        reply_text=turn.get("adversarial_reply_text", "Agendei. Vaga confirmada às 14h."),
        reply_parts=[{"kind": "phrase", "phrase": "help"}],
        appointment_preferences=turn.get("preferences"),
    )
    generator = _FixtureGenerator(decision)
    inbound = synthetic_message(f"turn-{number}", turn["customer_message"])
    reply = MessageResponder(
        store=store,
        generator=generator,
        safe_failure_reply="Falha sintética",
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
    ).handle(inbound, deadline=ExecutionDeadline.start())
    body = reply.body if reply else None
    active = store.list_active_handoffs()
    expected = turn["expected"]
    if case.kind == "handoff":
        checks = {
            "durable_handoff": bool(active) is expected["active"],
            "suppression": (reply is None) is expected["suppressed"],
        }
    else:
        claim = store.get_generation(provider="eval", provider_message_id=f"turn-{number}")
        intake = store.get_appointment_intake(inbound_message_id=claim.inbound_message_id)
        intake_matches = (
            intake is None
            if expected.get("intake_absent")
            else (
                intake is not None and intake.clarification_count == expected["clarification_count"]
            )
        )
        checks = {
            "no_booking_claim": body is not None
            and expected["contains"] in body
            and not any(
                text in body.casefold()
                for text in (
                    "agendei",
                    "vaga confirmada",
                    "vaga está reservada",
                    "horário está confirmado",
                    "temos horário às",
                    "pode vir sexta",
                )
            ),
            "handoff_policy": bool(active) is expected["handoff"],
            "bounded_intake": intake_matches,
        }
    return checks, body, generator.latencies


def dry_run(suite: EvalSuite, *, repetitions: int = 1, revision: str) -> RunRecord:
    if isinstance(repetitions, bool) or not 1 <= repetitions <= 100:
        raise ValueError("eval_invalid_repetitions")
    samples = []
    for case in suite.cases:
        for repetition in range(1, repetitions + 1):
            with TemporaryDirectory(prefix="rj-eval-") as temporary:
                directory = Path(temporary)
                database_path = directory / "synthetic.db"
                store = None
                if case.kind in {"appointment", "handoff", "context"}:
                    store = SqliteConversationStore(database_path)
                    store.initialize()
                for number, turn in enumerate(case.data.get("turns", [case.data]), 1):
                    started = perf_counter()
                    if case.kind in {"appointment", "handoff"}:
                        checks, body, latencies = _episode_turn(
                            case,
                            turn,
                            number,
                            store,
                            database_path,
                        )
                    elif case.kind == "context":
                        checks, body, latencies = prepare_context_case(case, store, directory)
                    else:
                        checks, body, latencies = _single_case(case)
                    samples.append(
                        Sample(
                            case_id=case.contract.case_id,
                            repetition=repetition,
                            turn=number,
                            status=("completed" if body else "suppressed")
                            if case.kind in {"appointment", "handoff"}
                            else "observed",
                            reply_hash=fingerprint(body) if body else None,
                            attempts=tuple(
                                Attempt(
                                    number=i,
                                    outcome="success",
                                    billable=False,
                                    input_tokens=None,
                                    output_tokens=None,
                                    latency_ms=latency,
                                )
                                for i, latency in enumerate(latencies, 1)
                            ),
                            e2e_latency_ms=(perf_counter() - started) * 1000,
                            checks={
                                key: "pass" if passed else "fail" for key, passed in checks.items()
                            },
                        )
                    )
    contracts = tuple(case.contract for case in suite.cases)
    configuration = ModelConfiguration(
        provider="deterministic",
        model="fixture-proposals-v1",
        thinking="disabled",
        structured_output=True,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        context_max_messages=12,
        context_token_budget=4000,
    )
    return RunRecord(
        schema_version=1,
        run_id=uuid4().hex,
        suite_id="v1",
        mode="deterministic",
        status="completed",
        created_at=datetime.now(UTC),
        revision=revision,
        configuration=configuration,
        repetitions=repetitions,
        total_cases=len(suite.cases),
        fingerprints=Fingerprints(
            suite=suite.digest,
            knowledge=suite.knowledge_digest,
            prompt=fingerprint([LiviaPersona().instructions, reply_plan_instructions()]),
        ),
        contracts=contracts,
        samples=tuple(samples),
        pricing=None,
        summary=summarize(samples, contracts),
    )
