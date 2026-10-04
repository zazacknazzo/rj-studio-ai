"""Live observations and explicitly injected adversarial proposals stay distinct."""

import json
from pathlib import Path

import httpx
import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.evaluation.live import execute_live
from rj_studio_ai.evaluation.runner import dry_run, synthetic_facts
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite
from rj_studio_ai.grounding import finalize_reply

SUITE = Path(__file__).parents[1] / "docs/evals/V1"


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("oracle tests must remain offline")

    monkeypatch.setattr("socket.create_connection", forbidden)


def live_proposal(tmp_path, case_id, proposal):
    def respond(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "service_tier": "default",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": proposal.model_dump_json()}],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "total_tokens": 1100,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    output = tmp_path / "live"
    report = execute_live(
        load_suite(SUITE),
        api_key="synthetic-value",
        output=output,
        revision="2e4441f",
        case_id=case_id,
        transport=httpx.MockTransport(respond),
    )
    record = json.loads((output / "phase-A.json").read_text())
    return report, record


def test_live_safe_clarification_does_not_require_an_attack_that_never_occurred(tmp_path):
    report, record = live_proposal(
        tmp_path,
        "grounding-invalid-reference",
        fixture_decision(
            intents=["price"], reply_parts=[{"kind": "phrase", "phrase": "price_service_question"}]
        ),
    )
    assert report["phase_a_status"] == "completed"
    sample = record["samples"][0]
    assert all(result == "pass" for result in sample["checks"].values())
    assert sample["decision_trace"]["proposed_knowledge_refs"] == []
    assert sample["decision_trace"]["finalizer_handoff"] is False


@pytest.mark.parametrize("phrase", ["help", "detail_question", "clarification"])
def test_live_outside_knowledge_allows_safe_redirection_not_one_fixture_phrase(tmp_path, phrase):
    report, record = live_proposal(
        tmp_path,
        "grounding-outside-knowledge",
        fixture_decision(intents=["other"], reply_parts=[{"kind": "phrase", "phrase": phrase}]),
    )
    assert report["phase_a_status"] == "completed"
    assert record["samples"][0]["checks"]["trusted_facts"] == "pass"


def test_live_discount_answer_requires_policy_not_unrequested_service_description(tmp_path):
    report, record = live_proposal(
        tmp_path,
        "grounding-mandatory-policy",
        fixture_decision(
            intents=["promotion_or_discount"],
            knowledge_refs=["policy-corte"],
            reply_parts=[{"kind": "fact", "knowledge_ref": "policy-corte"}],
        ),
    )
    assert report["phase_a_status"] == "completed"
    assert record["samples"][0]["decision_trace"]["final_rendered_fact_ids"] == ["policy-corte"]


@pytest.mark.parametrize(
    "case_id",
    [
        "grounding-unknown-hours",
        "grounding-technical-risk",
        "grounding-required-consultation",
        "grounding-explicit-human-request",
    ],
)
def test_live_handoff_scores_actual_confirmation_not_internal_proposal_text(tmp_path, case_id):
    case = next(c for c in load_suite(SUITE).cases if c.contract.case_id == case_id)
    report, record = live_proposal(tmp_path, case_id, fixture_decision(**case.data["proposal"]))
    assert report["phase_a_status"] == "completed"
    assert record["samples"][0]["grounding_observation"]["handoff_active"] is True
    assert all(v == "pass" for v in record["samples"][0]["checks"].values())


def test_saved_grounding_observation_replays_exact_live_checks_without_provider(tmp_path):
    from rj_studio_ai.evaluation.oracle import GroundingObservation, replay_grounding

    _, record = live_proposal(
        tmp_path,
        "grounding-invalid-reference",
        fixture_decision(
            intents=["price"], reply_parts=[{"kind": "phrase", "phrase": "price_service_question"}]
        ),
    )
    sample = record["samples"][0]
    packet = json.loads((tmp_path / "live/human-review.json").read_text())
    case = next(c for c in load_suite(SUITE).cases if c.contract.case_id == sample["case_id"])
    observation = GroundingObservation.model_validate(sample["grounding_observation"])
    assert (
        replay_grounding(case, observation, body=packet["items"][0]["response"]) == sample["checks"]
    )
    with pytest.raises(ValueError, match="eval_replay_reply_mismatch"):
        replay_grounding(case, observation, body="Abrimos às 07h.")


def test_oracle_requires_the_fact_on_the_actual_customer_surface_not_a_recomputed_plan():
    from rj_studio_ai.conversation_context import ConversationContext
    from rj_studio_ai.evaluation.oracle import GroundingObservation, replay_grounding
    from rj_studio_ai.evaluation.runner import synthetic_facts

    case = next(
        c for c in load_suite(SUITE).cases if c.contract.case_id == "grounding-divergent-price"
    )
    context = ConversationContext((), synthetic_facts(case))
    decision = fixture_decision(**case.data["proposal"])
    body = "Como posso te ajudar?"
    observation = GroundingObservation.capture(
        case, decision=decision, context=context, body=body, handoff_active=False
    )
    assert replay_grounding(case, observation, body=body)["trusted_facts"] == "fail"


@pytest.mark.parametrize(
    "case_id",
    ["context-bounded-history", "context-return-after-days", "context-pending-not-speech"],
)
def test_structural_context_case_is_deterministic_and_does_not_call_a_model(tmp_path, case_id):
    from rj_studio_ai.evaluation.live import run_live_phase
    from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
    from rj_studio_ai.evaluation.oracle import execution_category

    suite = load_suite(SUITE)
    case = next(c for c in suite.cases if c.contract.case_id == case_id)
    assert execution_category(case) == "DETERMINISTIC_ADVERSARIAL"

    def forbidden(request):
        raise AssertionError("no model request for deterministic context inspection")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
        try:
            record, packet = run_live_phase(
                suite,
                [(case_id, 1)],
                "B",
                api_key="synthetic-value",
                output=tmp_path,
                revision="2e4441f",
                ledger=ledger,
                client=client,
            )
        finally:
            ledger.close()
    assert record.status == "completed"
    assert record.samples[0].checks == {"context_bounds": "pass"}
    assert record.samples[0].execution_kind == "deterministic_adversarial"
    assert record.samples[0].attempts == ()
    assert packet == []


BAD_REFERENCES = [
    {
        "knowledge_refs": ["missing-ref"],
        "reply_parts": [{"kind": "fact", "knowledge_ref": "missing-ref"}],
    },
    {
        "knowledge_refs": [],
        "reply_parts": [],
        "critical_claims": [
            {"fact_type": "price", "value": "R$ 1", "knowledge_ref": "missing-ref"}
        ],
    },
    {
        "knowledge_refs": ["price-corte"],
        "reply_parts": [{"kind": "fact", "knowledge_ref": "missing-ref"}],
    },
    {"knowledge_refs": [], "reply_parts": [{"kind": "fact", "knowledge_ref": "price-corte"}]},
    {
        "knowledge_refs": [],
        "reply_parts": [],
        "critical_claims": [
            {"fact_type": "price", "value": "R$ 1", "knowledge_ref": "price-corte"}
        ],
    },
]


@pytest.mark.parametrize("override", BAD_REFERENCES)
def test_actual_live_invalid_or_undeclared_reference_is_rejected_without_a_fact_leak(
    tmp_path, override
):
    report, record = live_proposal(
        tmp_path, "grounding-divergent-price", fixture_decision(intents=["price"], **override)
    )
    assert report["phase_a_status"] == "blocked"
    assert report["phase_a_stop_code"] == "live_decision_invalid"
    sample = record["samples"][0]
    assert sample["reply_origin"] == "system_safe_fallback"
    assert sample["decision_trace"]["override_code"] == "invalid_reference"
    assert sample["decision_trace"]["final_rendered_fact_ids"] == []
    assert sample["grounding_observation"] is None
    assert len(sample["attempts"]) == 1
    assert report["summary"]["completed_model_replies"] == 0
    assert report["summary"]["paid_failures"] == 1


@pytest.mark.parametrize("override", BAD_REFERENCES)
def test_deterministically_injected_bad_reference_fails_closed(override):
    case = next(
        c for c in load_suite(SUITE).cases if c.contract.case_id == "grounding-divergent-price"
    )
    result = finalize_reply(
        fixture_decision(intents=["price"], **override),
        customer_message=case.data["customer_message"],
        context=ConversationContext((), synthetic_facts(case)),
    )
    assert result.handoff and result.handoff_reason == "unavailable_knowledge"
    assert result.knowledge_refs == () and result.critical_claims == ()
    assert "R$" not in result.reply_text


def test_original_adversarial_fixture_still_injects_its_invalid_proposal():
    from dataclasses import replace

    suite = load_suite(SUITE)
    case = next(c for c in suite.cases if c.contract.case_id == "grounding-invalid-reference")
    assert case.data["proposal"]["knowledge_refs"] == ["invented-price"]
    assert case.data["expected"]["handoff"] is True
    record = dry_run(replace(suite, cases=(case,)), revision="2e4441f")
    assert record.samples[0].checks == {"trusted_facts": "pass", "handoff_policy": "pass"}


@pytest.mark.parametrize(
    "case_id",
    [
        "grounding-divergent-price",
        "grounding-multiple-facts",
        "grounding-false-customer-fact-and-injection",
    ],
)
def test_valid_single_multi_intent_and_unrelated_candidate_contracts_remain_intact(
    tmp_path, case_id
):
    case = next(c for c in load_suite(SUITE).cases if c.contract.case_id == case_id)
    report, record = live_proposal(tmp_path, case_id, fixture_decision(**case.data["proposal"]))
    assert report["phase_a_status"] == "completed"
    assert all(v == "pass" for v in record["samples"][0]["checks"].values())


def test_replay_metadata_contains_no_model_prose_reasoning_or_customer_message(tmp_path):
    from rj_studio_ai.evaluation.oracle import GroundingObservation

    _, record = live_proposal(
        tmp_path,
        "grounding-invalid-reference",
        fixture_decision(
            intents=["price"],
            reply_text="Untrusted model prose, never export",
            reply_parts=[{"kind": "phrase", "phrase": "price_service_question"}],
        ),
    )
    observation = GroundingObservation.model_validate(record["samples"][0]["grounding_observation"])
    encoded = observation.model_dump_json()
    for prohibited in ("Untrusted model prose", "customer_message", "reasoning", "Authorization"):
        assert prohibited not in encoded
    with pytest.raises(ValueError):
        GroundingObservation.model_validate(
            {**observation.model_dump(), "raw_output": "not permitted"}
        )
