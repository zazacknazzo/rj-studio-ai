from pathlib import Path

import httpx

from rj_studio_ai.evaluation.live import LiveSample, execute_live, live_summary, run_live_phase
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing, Usage
from rj_studio_ai.evaluation.openai_live import LiveAttempt
from rj_studio_ai.evaluation.records import CaseContract, CheckContract, fingerprint
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
    assert result["summary"]["completed_replies"] == 0
    assert result["summary"]["completed_model_replies"] == 0
    assert result["summary"]["completed_logical_replies"] == 1
    assert result["summary"]["system_safe_fallbacks"] == 1
    assert result["summary"]["cost_per_1000_replies_usd"] is None
    assert result["summary"]["cost_denominator"] == "completed_model_replies"
    assert result["phase_summaries"]["A"] == result["summary"]
    assert result["phase_summaries"]["B"] is None
    assert result["summary"]["critical_failures"] == {"numerator": 2, "denominator": 2}
    assert result["summary"]["critical_not_evaluable"] == 2
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


def test_incomplete_generation_has_no_evaluable_persona_output(tmp_path):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
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
                    "output_tokens_details": {"reasoning_tokens": 133},
                },
                "output": [],
            },
        )

    ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        record, packet = run_live_phase(
            load_suite(Path("docs/evals/V1")),
            [("persona-incomplete-context", 1)],
            "A",
            api_key="synthetic-value",
            output=tmp_path,
            revision="486f6c3",
            ledger=ledger,
            client=client,
        )
    summary = live_summary(record.samples, record.contracts, ledger.pricing)
    assert record.status == "blocked"
    assert record.stop_code == "live_incomplete_output"
    assert record.samples[0].checks == {"persona_surface": "not_run"}
    assert summary["metrics"]["persona"] == {"numerator": 0, "denominator": 0}
    assert summary["persona"] == {"evaluable": 0, "pass": 0, "fail": 0, "not_evaluable": 1}
    assert summary["generation_failures"] == 1
    assert summary["system_safe_fallbacks"] == 1
    assert summary["completed_model_replies"] == 0
    assert packet == []
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
    assert record.configuration["max_output_tokens"] == 512
    assert live_summary(record.samples, record.contracts, ledger.pricing)["persona"] == {
        "evaluable": 1,
        "pass": 0,
        "fail": 1,
        "not_evaluable": 0,
    }
    ledger.close()


def test_paid_retry_and_fallback_cost_use_only_completed_model_reply_denominator():
    usage = Usage(
        input_tokens=1000,
        cached_tokens=0,
        cache_write_tokens=0,
        output_tokens=200,
        reasoning_tokens=133,
    )
    failed = LiveAttempt(
        number=1,
        outcome="failure",
        billable=True,
        input_tokens=1000,
        output_tokens=200,
        usage=usage,
        latency_ms=100.0,
        error_code="live_incomplete_output",
    )
    successful = failed.model_copy(update={"number": 2, "outcome": "success", "error_code": None})
    fallback = LiveSample(
        case_id="persona-synthetic",
        repetition=1,
        turn=1,
        status="completed",
        reply_origin="system_safe_fallback",
        reply_hash=fingerprint("fallback sintético"),
        attempts=(failed,),
        e2e_latency_ms=120.0,
        checks={"persona_surface": "not_run"},
        execution_kind="live_generation",
    )
    model_reply = fallback.model_copy(
        update={
            "repetition": 2,
            "reply_origin": "model",
            "attempts": (failed, successful),
            "e2e_latency_ms": 250.0,
            "checks": {"persona_surface": "pass"},
        }
    )
    contract = CaseContract(
        case_id="persona-synthetic",
        turns=1,
        checks={"persona_surface": CheckContract(metric="persona")},
    )
    report = live_summary([fallback, model_reply], [contract], LivePricing.load())
    assert report["completed_logical_replies"] == 2
    assert report["completed_model_replies"] == 1
    assert report["system_safe_fallbacks"] == 1
    assert report["live_calls"] == 3
    assert report["retries"] == 1
    assert report["paid_failures"] == 2
    assert report["estimated_cost_usd"] == 0.012
    assert report["cost_per_1000_replies_usd"] == 12.0
    assert report["cost_denominator"] == "completed_model_replies"
    assert report["persona"] == {"evaluable": 1, "pass": 1, "fail": 0, "not_evaluable": 1}
    assert report["run_count"] == 2


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
