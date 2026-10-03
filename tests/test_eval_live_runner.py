import json
from pathlib import Path

import httpx
import pytest

from rj_studio_ai.evaluation.live import (
    SMOKE_CASES,
    LiveRecord,
    LiveSample,
    execute_live,
    live_summary,
    run_live_phase,
)
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing, Usage
from rj_studio_ai.evaluation.openai_live import LiveAttempt
from rj_studio_ai.evaluation.records import CaseContract, CheckContract, fingerprint
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


def test_passing_ten_case_smoke_stops_before_phase_b_with_one_dollar_cap(tmp_path):
    suite = load_suite(Path("docs/evals/V1"))
    by_id = {c.contract.case_id: c for c in suite.cases}
    proposals = []
    for identifier in SMOKE_CASES:
        case = by_id[identifier]
        if case.kind == "grounding":
            proposals.append(fixture_decision(**case.data["proposal"]))
        elif case.kind == "appointment":
            turn = case.data["turns"][0]
            proposals.append(
                fixture_decision(
                    intents=turn.get("expected_intents", ["appointment_interest"]),
                    appointment_preferences=turn.get("preferences"),
                )
            )
        else:
            proposals.append(
                fixture_decision(reply_parts=[{"kind": "phrase", "phrase": "clarification"}])
            )
    calls = []

    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        decision = proposals[len(calls)]
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

    report = execute_live(
        suite,
        api_key="synthetic-value",
        output=tmp_path / "smoke",
        revision="2002de4",
        transport=httpx.MockTransport(transport),
        smoke_only=True,
    )
    assert report["phase_a_status"] == "completed"
    assert report["phase_b_executed"] is False
    assert report["execution_scope"] == "smoke_only"
    assert report["global_cap_usd"] == report["phase_a_cap_usd"] == 1
    assert report["summary"]["live_calls"] == len(calls) == 10
    assert report["summary"]["retries"] == 0
    assert report["ticket_status"] == "in-progress"
    record = json.loads((tmp_path / "smoke" / "phase-A.json").read_text())
    assert [s["case_id"] for s in record["samples"]] == list(SMOKE_CASES)
    assert not (tmp_path / "smoke" / "phase-B.json").exists()


@pytest.mark.parametrize(
    "usage", [None, {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}]
)
def test_unknown_usage_stops_after_one_attempt_without_approving_smoke_or_b(tmp_path, usage):
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
                "usage": usage,
            },
        )

    output = tmp_path / "unknown"
    report = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=output,
        revision="782870c",
        transport=httpx.MockTransport(transport),
    )
    assert len(calls) == 1
    assert report["phase_a_status"] == "blocked"
    assert report["phase_b_executed"] is False
    assert report["summary"]["completed_model_replies"] == 0
    assert report["summary"]["estimated_cost_usd"] is None
    assert report["summary"]["cost_per_1000_replies_usd"] is None
    journal = [json.loads(line) for line in (output / "spend.jsonl").read_text().splitlines()]
    assert report["budget_upper_bound_usd"] == float(journal[1]["reserved_usd"])
    assert journal[-1] == {"kind": "settle", "usage": None}
    assert not (output / "phase-B.json").exists()
    reopened = BudgetLedger(output / "spend.jsonl", LivePricing.load())
    with pytest.raises(ValueError, match="unresolved_submission"):
        reopened.reserve("A", input_bound=1000, output_bound=512)
    reopened.close()


def test_reasoning_count_can_remain_unknown_with_complete_pricing_evidence(tmp_path):
    case = next(
        c
        for c in load_suite(Path("docs/evals/V1")).cases
        if c.contract.case_id == "grounding-multiple-facts"
    )
    decision = fixture_decision(**case.data["proposal"])

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
                                "text": decision.model_dump_json(),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "total_tokens": 1100,
                    "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
                },
            },
        )

    output = tmp_path / "known-cost"
    report = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=output,
        revision="782870c",
        case_id="grounding-multiple-facts",
        transport=httpx.MockTransport(transport),
    )
    assert report["phase_a_status"] == "completed"
    assert report["phase_b_executed"] is False
    assert report["summary"]["reasoning_tokens"] is None
    assert report["summary"]["estimated_cost_usd"] == 0.00277
    assert report["summary"]["completed_model_replies"] == 1
    record = json.loads((output / "phase-A.json").read_text())
    attempt = record["samples"][0]["attempts"][0]
    assert attempt["response_diagnostics"]["reasoning_tokens_present"] is False
    assert attempt["usage"]["reasoning_tokens"] is None
    assert record["schema_version"] == 5
    attempt.pop("response_diagnostics")
    with pytest.raises(ValueError, match="live_missing_response_diagnostics"):
        LiveRecord.model_validate(record)
    record["schema_version"] = 4
    assert LiveRecord.model_validate(record).schema_version == 4


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


def test_preflight_failure_keeps_durable_fallback_separate_without_paid_generation(tmp_path):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(503, json={"error": "synthetic preflight failure"})

    result = execute_live(
        load_suite(Path("docs/evals/V1")),
        api_key="synthetic-value",
        output=tmp_path / "run",
        revision="93b83eb",
        transport=httpx.MockTransport(transport),
    )
    assert len(requests) == 1
    assert requests[0].url.path.endswith("input_tokens")
    assert result["phase_a_status"] == "blocked"
    assert result["phase_b_executed"] is False
    summary = result["summary"]
    assert summary["live_calls"] == 0
    assert summary["paid_failures"] == 0
    assert summary["completed_model_replies"] == 0
    assert summary["system_safe_fallbacks"] == 1
    assert summary["completed_logical_replies"] == 1
    assert summary["generation_failures"] == 1
    assert summary["estimated_cost_usd"] == 0.0
    assert summary["cost_per_1000_replies_usd"] is None
    assert summary["deterministic_guard_turns"] == 0
    assert summary["critical_not_evaluable"] == 2
    assert summary["critical_failures"] == {"numerator": 2, "denominator": 2}


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
