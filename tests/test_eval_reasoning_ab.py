"""Eval-only effort and pairwise budget boundaries; no production provider changes."""

import json
from decimal import Decimal

import httpx
import pytest
from test_eval_openai_live import response_payload

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.openai_live import OpenAIEvalGenerator


def test_effort_is_only_request_difference_and_metrics_are_truthful(tmp_path):
    payloads = []
    for effort in ("medium", "low"):

        def respond(request):
            if request.url.path.endswith("input_tokens"):
                return httpx.Response(200, json={"input_tokens": 1000})
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json=response_payload())

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            ledger = BudgetLedger(tmp_path / f"{effort}.jsonl", LivePricing.load())
            try:
                generator = OpenAIEvalGenerator(
                    api_key="synthetic-value",
                    client=client,
                    ledger=ledger,
                    phase="A",
                    reasoning_effort=effort,
                )
                result = generator.generate(
                    InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
                    context=ConversationContext((), ()),
                    remaining_budget=29,
                )
                assert (
                    result.metric.configuration
                    == f"effort={effort};tier=default;max_output_tokens=1024"
                )
            finally:
                ledger.close()
    assert payloads[0].pop("reasoning") == {"effort": "medium"}
    assert payloads[1].pop("reasoning") == {"effort": "low"}
    assert payloads[0] == payloads[1]


def test_invalid_effort_is_rejected_before_transport(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.jsonl", LivePricing.load())
    try:
        with (
            httpx.Client() as client,
            pytest.raises(ValueError, match="invalid_eval_reasoning_effort"),
        ):
            OpenAIEvalGenerator(
                api_key="synthetic-value",
                client=client,
                ledger=ledger,
                phase="A",
                reasoning_effort="high",
            )
    finally:
        ledger.close()


def test_pair_admission_uses_actual_settlements_not_all_future_reserves(tmp_path):
    from rj_studio_ai.evaluation.live_billing import Usage
    from rj_studio_ai.evaluation.reasoning_ab import admit_next_pair

    ledger = BudgetLedger(
        tmp_path / "pair.jsonl",
        LivePricing.load(),
        phase_a_cap=Decimal("0.30"),
        global_cap=Decimal("0.30"),
    )
    try:
        for _ in range(10):
            admission = admit_next_pair(ledger)
            assert admission["maximum_safe_reservation_usd"] == "0.1056"
            for _ in range(2):
                ledger.reserve("A", input_bound=2024, output_bound=1024)
                ledger.settle(
                    Usage(
                        input_tokens=1000,
                        cached_tokens=0,
                        cache_write_tokens=0,
                        output_tokens=100,
                        reasoning_tokens=40,
                    )
                )
        assert ledger.charged["A"] == Decimal("0.060")
        ledger.charged["A"] = Decimal("0.195")
        with pytest.raises(ValueError, match="pair_budget_exhausted"):
            admit_next_pair(ledger)
        assert ledger.outstanding is None
    finally:
        ledger.close()


def proposals():
    from test_commercial_live_retest import decision

    from rj_studio_ai.evaluation.suite import fixture_decision

    clarify = decision(1)
    return [
        decision(0),
        clarify,
        clarify,
        decision(2),
        fixture_decision(
            surface="agentic",
            intents=["technical_guidance"],
            handoff=True,
            handoff_reason="technical_risk",
        ),
        fixture_decision(
            surface="agentic",
            intents=["human_request"],
            handoff=True,
            handoff_reason="explicit_human_request",
        ),
        fixture_decision(
            surface="agentic",
            intents=["appointment_interest"],
            appointment_preferences={"desired_service": "corte", "preferred_day": "sexta"},
            reply_parts=[
                {
                    "kind": "conversation",
                    "purpose": "question",
                    "targets": ["preferred_time"],
                    "text": "Você prefere manhã ou tarde?",
                }
            ],
        ),
        fixture_decision(
            surface="agentic",
            intents=["appointment_change"],
            reply_parts=[
                {
                    "kind": "conversation",
                    "purpose": "recovery",
                    "targets": ["cancellation_choice"],
                    "text": "Você gostaria de tentar outro dia antes de cancelar?",
                }
            ],
        ),
        fixture_decision(
            surface="agentic",
            next_action="clarify",
            reply_parts=[
                {
                    "kind": "conversation",
                    "purpose": "clarification",
                    "information_targets": ["service"],
                    "text": "Qual serviço você tem em mente para amanhã?",
                }
            ],
        ),
        fixture_decision(
            surface="agentic",
            intents=["price", "hours"],
            knowledge_refs=["price-corte", "hours-corte"],
            reply_parts=[
                {"kind": "fact", "knowledge_ref": "price-corte"},
                {"kind": "fact", "knowledge_ref": "hours-corte"},
            ],
        ),
    ]


def run_ab(tmp_path, failure=None):
    from pathlib import Path

    from rj_studio_ai.evaluation.reasoning_ab import execute_ab
    from rj_studio_ai.evaluation.suite import load_suite

    calls = []
    choices = proposals()

    def respond(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        index = len(calls)
        calls.append(json.loads(request.content))
        proposal = choices[index // 2]
        payload = response_payload(
            output=[
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": proposal.model_dump_json()}],
                }
            ]
        )
        if index == 1 and failure == "unknown":
            payload["usage"] = None
        if index == 1 and failure == "incomplete":
            payload.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        if index == 1 and failure == "critical":
            payload["output"][0]["content"][0]["text"] = choices[1].model_dump_json()
        return httpx.Response(200, json=payload)

    output = tmp_path / "ab"
    report = execute_ab(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=output,
        revision="82afec4",
        transport=httpx.MockTransport(respond),
    )
    return calls, report, output


def test_twenty_calls_are_interleaved_comparable_and_share_actual_budget(tmp_path):
    calls, report, output = run_ab(tmp_path)
    assert len(calls) == 20, report
    assert report["completed_pairs"] == 10 and report["stop_code"] is None
    assert [c["reasoning"]["effort"] for c in calls] == ["medium", "low"] * 10
    for medium, low in zip(calls[::2], calls[1::2], strict=True):
        medium = {k: v for k, v in medium.items() if k != "reasoning"}
        low = {k: v for k, v in low.items() if k != "reasoning"}
        assert medium == low
    assert report["actual_cost_usd"] == "0.05540"
    assert report["low_minus_medium"]["reasoning_tokens"] == 0
    assert report["low_minus_medium"]["output_tokens"] == 0
    assert report["low_minus_medium"]["estimated_cost_usd"] == 0
    assert report["low_minus_medium"]["matched_population"] is True
    assert report["cap_usd"] == "0.30" and not report["phase_b_executed"]
    assert all(a["maximum_safe_reservation_usd"] == "0.1056" for a in report["admissions"])
    assert all(
        arm["completed_model_replies"] == 10 and arm["retries"] == 0
        for arm in report["arms"].values()
    )
    for record in output.glob("*-low/phase-A.json"):
        assert json.loads(record.read_text())["configuration"]["reasoning_effort"] == "low"
    form = (output / "human-review-formulario.md").read_text()
    assert form.count("## CASO ") == 10
    assert not any(
        s in form for s in ("medium", "low", "reasoning", "gpt-", "tokens", "synthetic-value")
    )
    assert len(json.loads((output / "human-review-mapping.json").read_text())) == 10


@pytest.mark.parametrize(
    "failure,code", [("unknown", "live_usage_absent"), ("incomplete", "live_incomplete_output")]
)
def test_failed_low_stops_without_retry_or_new_pair_and_keeps_accounting(tmp_path, failure, code):
    calls, report, output = run_ab(tmp_path, failure)
    assert len(calls) == 2 and report["completed_pairs"] == 0
    assert report["stop_code"] == code
    assert len(json.loads((output / "01-medium/trusted-response.json").read_text())) == 1
    assert json.loads((output / "01-low/trusted-response.json").read_text()) == []
    assert report["low_minus_medium"]["matched_population"] is False
    low = report["arms"]["low"]
    assert low["completed_model_replies"] == 0 and low["system_safe_fallbacks"] == 1
    assert low["retries"] == 0 and not report["phase_b_executed"]
    if failure == "unknown":
        assert report["actual_cost_usd"] is None
        assert Decimal(report["budget_upper_bound_usd"]) == Decimal("0.01807")
    else:
        assert low["paid_failures"] == 1
        sample = json.loads((output / "01-low/phase-A.json").read_text())["samples"][0]
        assert (
            sample["attempts"][0]["response_diagnostics"]["incomplete_reason"]
            == "max_output_tokens"
        )


def test_pair_request_mismatch_is_detected_before_submission():
    from rj_studio_ai.evaluation.reasoning_ab import PairRequests

    comparison = PairRequests()
    for path in ("input_tokens", ""):
        url = "https://api.openai.com/v1/responses" + ("/" + path if path else "")
        comparison.check(
            httpx.Request("POST", url, json={"reasoning": {"effort": "medium"}, "input": "same"})
        )
    comparison.effort = "low"
    with pytest.raises(ValueError, match="ab_configuration_mismatch"):
        comparison.check(
            httpx.Request(
                "POST",
                "https://api.openai.com/v1/responses/input_tokens",
                json={"reasoning": {"effort": "low"}, "input": "different"},
            )
        )


def test_unknown_reservation_blocks_pair_and_never_becomes_zero(tmp_path):
    from rj_studio_ai.evaluation.reasoning_ab import admit_next_pair

    ledger = BudgetLedger(
        tmp_path / "unknown.jsonl",
        LivePricing.load(),
        phase_a_cap=Decimal("0.30"),
        global_cap=Decimal("0.30"),
    )
    try:
        ledger.reserve("A", input_bound=2024, output_bound=1024)
        ledger.settle(None)
        with pytest.raises(ValueError, match="unresolved_submission"):
            admit_next_pair(ledger)
        assert ledger.upper_bound_usd == Decimal("0.0153")
    finally:
        ledger.close()


def test_critical_low_regression_rejects_and_stops_before_next_pair(tmp_path):
    calls, report, _ = run_ab(tmp_path, "critical")
    assert len(calls) == 2
    assert report["stop_code"] == "critical_failure" and report["stop_effort"] == "low"
    assert report["recommendation"] == "MEDIUM WINS"
    assert report["recommendation_reason"].startswith("LOW REJECT")
    assert report["arms"]["low"]["critical_failures"]["numerator"] > 0
    assert not report["phase_b_executed"]


def test_budget_block_stops_before_either_arm(tmp_path, monkeypatch):
    from rj_studio_ai.evaluation import reasoning_ab

    def blocked(ledger):
        ledger.charged["A"] = Decimal("0.195")
        return original(ledger)

    original = reasoning_ab.admit_next_pair
    monkeypatch.setattr(reasoning_ab, "admit_next_pair", blocked)
    calls, report, _ = run_ab(tmp_path)
    assert not calls and report["completed_pairs"] == 0
    assert report["stop_code"] == "pair_budget_exhausted"


def test_latency_is_observed_without_changing_gate_or_naturalness_approval():
    from rj_studio_ai.evaluation.live import _measured_latency_gate
    from rj_studio_ai.evaluation.reasoning_ab import recommendation

    arms = {
        "medium": {"billable_e2e_p95_ms": 15000},
        "low": {"billable_e2e_p95_ms": 12000, "metrics": {}},
    }
    assert recommendation(arms, 10, None, None)[0] == "LOW WINS"
    assert "human" in recommendation(arms, 10, None, None)[1]
    assert (
        _measured_latency_gate({"billable_e2e_p95_ms": 12000, "unknown_billing_attempts": 0})
        == "fail"
    )
    assert recommendation(arms, 5, None, None)[0] == "INCONCLUSIVE"
