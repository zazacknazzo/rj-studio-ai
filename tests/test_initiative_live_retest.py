"""Four-case gate is bounded and never unlocks Phase B, including on paid failure."""

import json
from pathlib import Path

import httpx
import pytest
from test_commercial_live_retest import decision

from rj_studio_ai.evaluation.live import execute_live
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


def run(tmp_path, *, incomplete=False, fail_budget=False, monkeypatch=None):
    if fail_budget:
        from decimal import Decimal

        from rj_studio_ai.evaluation.live_billing import BudgetLedger

        reserve = BudgetLedger.reserve

        def exhausted(ledger, *args, **kwargs):
            assert ledger.phase_a_cap == ledger.global_cap == Decimal("0.40")
            ledger.charged["A"] = Decimal("0.399")
            return reserve(ledger, *args, **kwargs)

        monkeypatch.setattr(BudgetLedger, "reserve", exhausted)
    calls = []

    def respond(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        index = len(calls)
        calls.append(True)
        proposal = (
            decision(index)
            if index < 3
            else fixture_decision(
                surface="agentic",
                intents=["technical_guidance"],
                next_action="request_human_attention",
                handoff=True,
                handoff_reason="technical_risk",
            )
        )
        failed = incomplete and index == 3
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "service_tier": "default",
                "status": "incomplete" if failed else "completed",
                "incomplete_details": {"reason": "max_output_tokens"} if failed else None,
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 1024 if failed else 100,
                    "total_tokens": 2024 if failed else 1100,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 500 if failed else 0},
                },
                "output": []
                if failed
                else [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": proposal.model_dump_json(),
                            }
                        ],
                    }
                ],
            },
        )

    output = tmp_path / "retest"
    report = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=output,
        revision="12c652c",
        initiative_only=True,
        phase_b_authorized=True,
        transport=httpx.MockTransport(respond),
    )
    record = json.loads((output / "phase-A.json").read_text())
    return calls, report, record


def test_four_case_retest_uses_shared_cap_and_no_phase_b(tmp_path):
    calls, report, record = run(tmp_path)
    assert len(calls) == 4 and report["phase_a_status"] == "completed"
    assert report["phase_a_cap_usd"] == report["global_cap_usd"] == 0.40
    assert report["execution_scope"] == "initiative_retest"
    assert [s["case_id"] for s in record["samples"]] == [
        "grounding-divergent-price",
        "grounding-unknown-price",
        "grounding-unauthorized-discount",
        "grounding-technical-risk",
    ]
    assert record["configuration"]["max_output_tokens"] == 1024
    assert record["configuration"]["observation_deadline_seconds"] == 30
    assert all(v == "pass" for s in record["samples"] for v in s["checks"].values())
    assert report["summary"]["retries"] == 0 and not report["phase_b_executed"]


def test_incomplete_risk_case_keeps_paid_cost_safe_fallback_and_stops(tmp_path):
    calls, report, record = run(tmp_path, incomplete=True)
    assert len(calls) == 4
    assert report["phase_a_status"] == "blocked"
    assert report["phase_a_stop_code"] == "live_incomplete_output"
    summary = report["summary"]
    assert summary["paid_failures"] == summary["system_safe_fallbacks"] == 1
    assert summary["completed_model_replies"] == 3
    assert summary["estimated_cost_usd"] == 0.02124
    assert summary["retries"] == 0 and not report["phase_b_executed"]
    sample = record["samples"][-1]
    assert sample["decision_trace"]["authorized_handoff"] is True
    assert sample["attempts"][0]["response_diagnostics"]["incomplete_reason"] == "max_output_tokens"


def test_1024_reservation_cannot_cross_shared_040_cap(tmp_path, monkeypatch):
    calls, report, _ = run(tmp_path, fail_budget=True, monkeypatch=monkeypatch)
    assert not calls
    assert report["phase_a_status"] == "budget_exhausted"
    assert report["budget_upper_bound_usd"] <= 0.40


@pytest.mark.parametrize(
    "other",
    [{"commercial_only": True}, {"smoke_only": True}, {"case_id": "grounding-multiple-facts"}],
)
def test_initiative_retest_cannot_expand_into_another_scope(tmp_path, other):
    with pytest.raises(ValueError, match="conflicting_execution_scope"):
        execute_live(
            load_suite(Path("docs/evals/V1")),
            api_key="synthetic-value",
            output=tmp_path / "bad",
            revision="12c652c",
            initiative_only=True,
            **other,
        )
    assert not (tmp_path / "bad").exists()
