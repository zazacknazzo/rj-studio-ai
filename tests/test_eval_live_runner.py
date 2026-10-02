from pathlib import Path

import httpx

from rj_studio_ai.evaluation.live import execute_live, run_live_phase
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


def test_paid_incomplete_output_stops_smoke_keeps_failure_and_never_starts_suite(tmp_path):
    calls = []

    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "gpt-6.1-sol",
                "service_tier": "default",
                "status": "incomplete",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "total_tokens": 1200,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 200},
                },
                "output": [],
            },
        )

    result = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=tmp_path / "run",
        revision="2534ceb",
        transport=httpx.MockTransport(transport),
    )
    assert len(calls) == 1
    assert result["phase_b_executed"] is False
    assert result["summary"]["paid_failures"] == 1
    assert result["summary"]["input_tokens"] == 1000
    assert result["summary"]["output_tokens"] == 200
    assert result["summary"]["estimated_cost_usd"] == 0.004
    assert result["phase_a_status"] == "blocked"
    assert (tmp_path / "run" / "human-review.md").exists()


def test_context_live_generation_and_pending_barrier_are_distinct(tmp_path):
    calls = []

    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
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
                        "content": [
                            {"type": "output_text", "text": fixture_decision().model_dump_json()}
                        ],
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

    suite = load_suite(Path("docs/evals/V1"))
    ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        record, _ = run_live_phase(
            suite,
            [(c.contract.case_id, 1) for c in suite.cases if c.kind == "context"],
            "B",
            api_key="synthetic-value",
            output=tmp_path,
            revision="2534ceb",
            ledger=ledger,
            client=client,
        )
    assert record.status == "completed"
    assert len(calls) == 2
    assert [s.execution_kind for s in record.samples] == [
        "live_generation",
        "live_generation",
        "delivery_barrier",
    ]
    assert all(s.checks["context_bounds"] == "pass" for s in record.samples)
    ledger.close()


def test_failed_noncritical_smoke_check_blocks_phase_a(tmp_path):
    def transport(request):
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
                        "content": [
                            {
                                "type": "output_text",
                                "text": fixture_decision(
                                    reply_parts=[{"kind": "phrase", "phrase": "greeting"}]
                                ).model_dump_json(),
                            }
                        ],
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

    ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        record, _ = run_live_phase(
            load_suite(Path("docs/evals/V1")),
            [("persona-incomplete-context", 1)],
            "A",
            api_key="synthetic-value",
            output=tmp_path,
            revision="2534ceb",
            ledger=ledger,
            client=client,
        )
    assert record.status == "blocked"
    assert record.stop_code == "smoke_check_failure"
    ledger.close()


def test_trusted_facts_with_wrong_multi_intent_do_not_pass_smoke(tmp_path):
    decision = fixture_decision(
        intents=["other"],
        knowledge_refs=["price-corte", "hours-corte"],
        reply_parts=[
            {"kind": "fact", "knowledge_ref": ref} for ref in ("price-corte", "hours-corte")
        ],
    )

    def transport(request):
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
                        "content": [{"type": "output_text", "text": decision.model_dump_json()}],
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

    ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        record, _ = run_live_phase(
            load_suite(Path("docs/evals/V1")),
            [("grounding-multiple-facts", 1)],
            "A",
            api_key="synthetic-value",
            output=tmp_path,
            revision="2534ceb",
            ledger=ledger,
            client=client,
        )
    assert record.status == "blocked"
    assert record.samples[0].checks == {
        "trusted_facts": "pass",
        "handoff_policy": "pass",
        "decision_contract": "fail",
    }
    ledger.close()
