"""No real requests: the three-case gate shares one ledger and never opens Phase B."""

import json
from pathlib import Path

import httpx
import pytest

from rj_studio_ai.evaluation.live import COMMERCIAL_RETEST_CASES, execute_live
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


def decision(index, generic=False):
    if index == 0:
        return fixture_decision(
            surface="agentic",
            intents=["price"],
            knowledge_refs=["price-corte"],
            reply_parts=[{"kind": "fact", "knowledge_ref": "price-corte"}],
        )
    return fixture_decision(
        surface="agentic",
        intents=["price" if index == 1 else "promotion_or_discount"],
        next_action="clarify",
        reply_parts=[
            {
                "kind": "conversation",
                "purpose": "clarification",
                "targets": [],
                "information_targets": ["service"],
                "text": "Posso ajudar com outra dúvida?"
                if generic
                else "Qual serviço você tem em mente?",
            }
        ],
    )


def run(tmp_path, *, generic=False, usage=True, oversized_preflight=False):
    calls = []

    def respond(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"input_tokens": 1_000_000 if oversized_preflight else 1000}
            )
        proposal = decision(len(calls), generic)
        calls.append(request)
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
                }
                if usage
                else None,
            },
        )

    output = tmp_path / "retest"
    report = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=output,
        revision="f6fead6",
        commercial_only=True,
        phase_b_authorized=True,
        transport=httpx.MockTransport(respond),
    )
    record = json.loads((output / "phase-A.json").read_text())
    return calls, report, record


def test_three_case_retest_shared_cap_no_retries_and_no_phase_b(tmp_path):
    calls, report, record = run(tmp_path)
    assert len(calls) == 3 and report["phase_a_status"] == "completed"
    assert report["phase_a_cap_usd"] == report["global_cap_usd"] == 0.30
    assert report["execution_scope"] == "commercial_retest"
    assert [s["case_id"] for s in record["samples"]] == list(COMMERCIAL_RETEST_CASES)
    assert all(v == "pass" for s in record["samples"] for v in s["checks"].values())
    assert report["summary"]["retries"] == 0 and not report["phase_b_executed"]
    assert report["summary"]["metrics"]["commercial"] == {"numerator": 2, "denominator": 2}


def test_generic_fallback_is_not_a_successful_retest_and_stops_before_third_call(tmp_path):
    calls, report, record = run(tmp_path, generic=True)
    assert len(calls) == 2 and report["phase_a_status"] == "blocked"
    assert report["phase_a_stop_code"] == "behavioral_failure"
    assert record["samples"][-1]["checks"]["trusted_facts"] == "pass"
    assert record["samples"][-1]["checks"]["general_clarification"] == "fail"
    assert not report["phase_b_executed"]


def test_three_case_gate_retains_usage_fail_closed_and_never_retries(tmp_path):
    calls, report, _ = run(tmp_path, usage=False)
    assert len(calls) == 1 and report["phase_a_status"] == "blocked"
    assert not report["phase_b_executed"]


def test_three_case_budget_blocks_generation_if_reservation_exceeds_shared_cap(
    tmp_path, monkeypatch
):
    from decimal import Decimal

    from rj_studio_ai.evaluation.live_billing import BudgetLedger

    original = BudgetLedger.reserve

    def exhausted(ledger, *args, **kwargs):
        assert ledger.global_cap == ledger.phase_a_cap == Decimal("0.30")
        ledger.charged["A"] = Decimal("0.299")
        return original(ledger, *args, **kwargs)

    monkeypatch.setattr(BudgetLedger, "reserve", exhausted)
    calls, report, _ = run(tmp_path)
    assert not calls and report["phase_a_status"] == "budget_exhausted"
    assert report["budget_upper_bound_usd"] <= 0.30


@pytest.mark.parametrize("other", [{"smoke_only": True}, {"case_id": "grounding-multiple-facts"}])
def test_commercial_scope_cannot_accidentally_expand(tmp_path, other):
    with pytest.raises(ValueError, match="conflicting_execution_scope"):
        execute_live(
            load_suite(Path("docs/evals/V1")),
            api_key="synthetic-value",
            output=tmp_path / "bad",
            revision="f6fead6",
            commercial_only=True,
            **other,
        )
    assert not (tmp_path / "bad").exists()
