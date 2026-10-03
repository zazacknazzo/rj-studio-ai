import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from rj_studio_ai import application, persistence
from rj_studio_ai.evaluation import live, openai_live
from rj_studio_ai.evaluation.suite import fixture_decision, load_suite


class Clock:
    value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def run_observed_case(
    tmp_path,
    monkeypatch,
    *,
    model_seconds,
    preflight_seconds=1,
    honor_read_timeout=True,
    advance_utc=False,
    validation_seconds=0,
    finalization_seconds=0,
):
    clock = Clock()
    monkeypatch.setattr(live, "monotonic", clock, raising=False)
    monkeypatch.setattr(live, "perf_counter", clock)
    monkeypatch.setattr(openai_live, "monotonic", clock)
    if validation_seconds:
        validate = openai_live.validate_llm_decision

        def timed_validation(*args, **kwargs):
            decision = validate(*args, **kwargs)
            clock.advance(validation_seconds)
            return decision

        monkeypatch.setattr(openai_live, "validate_llm_decision", timed_validation)
    if finalization_seconds:
        finalize = application.finalize_reply

        def timed_finalization(*args, **kwargs):
            finalized = finalize(*args, **kwargs)
            clock.advance(finalization_seconds)
            return finalized

        monkeypatch.setattr(application, "finalize_reply", timed_finalization)
    if advance_utc:
        epoch = datetime.now(UTC)

        class UtcClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return (epoch + timedelta(seconds=clock.value)).astimezone(tz)

        monkeypatch.setattr(persistence, "datetime", UtcClock)
    suite = load_suite(Path("docs/evals/V1"))
    case = next(c for c in suite.cases if c.contract.case_id == "grounding-multiple-facts")
    proposal = fixture_decision(**case.data["proposal"])
    requests = []

    def transport(request):
        requests.append(request)
        timeout = request.extensions["timeout"]
        if request.url.path.endswith("input_tokens"):
            clock.advance(min(preflight_seconds, timeout["read"]))
            if preflight_seconds > timeout["read"]:
                raise httpx.ReadTimeout("synthetic preflight timeout")
            return httpx.Response(200, json={"input_tokens": 1000})
        clock.advance(min(model_seconds, timeout["read"]) if honor_read_timeout else model_seconds)
        if honor_read_timeout and model_seconds > timeout["read"]:
            raise httpx.ReadTimeout("synthetic observation timeout")
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
                    "output_tokens_details": {"reasoning_tokens": 40},
                },
            },
        )

    output = tmp_path / "observation"
    report = live.execute_live(
        suite,
        api_key="synthetic-value",
        output=output,
        revision="80ada33",
        case_id="grounding-multiple-facts",
        transport=httpx.MockTransport(transport),
    )
    record = json.loads((output / "phase-A.json").read_text())
    return report, record, requests


def test_twelve_second_reply_preserves_usage_but_fails_eight_second_gate(tmp_path, monkeypatch):
    report, record, requests = run_observed_case(tmp_path, monkeypatch, model_seconds=12)
    assert report["phase_a_status"] == "completed"
    assert report["phase_a_stop_code"] is None
    assert report["phase_b_executed"] is False
    summary = report["summary"]
    assert summary["completed_model_replies"] == 1
    assert summary["paid_failures"] == summary["retries"] == 0
    assert summary["input_tokens"] == 1000
    assert summary["output_tokens"] == 100
    assert summary["model_p95_ms"] == 12000
    assert summary["billable_e2e_p95_ms"] == 13000  # Counting remains inside E2E.
    assert report["latency_threshold_ms"] == 8000
    assert report["measured_latency_gate"] == "fail"
    assert report["operational_latency_gate"] == "pending_real_provider_evidence"
    sample = record["samples"][0]
    assert sample["attempts"][0]["response_diagnostics"]["response_status"] == "completed"
    assert sample["attempts"][0]["usage"]["reasoning_tokens"] == 40
    assert all(value == "pass" for value in sample["checks"].values())
    assert record["configuration"]["observation_deadline_seconds"] == 30
    assert len(requests) == 2


@pytest.mark.parametrize("stage", ["validation", "finalization"])
def test_post_response_budget_exhaustion_preserves_evidence_without_retry(
    tmp_path, monkeypatch, stage
):
    report, record, requests = run_observed_case(
        tmp_path,
        monkeypatch,
        model_seconds=27.9,
        advance_utc=True,
        **{stage + "_seconds": 0.2},
    )
    assert report["phase_a_status"] == "blocked"
    assert report["phase_a_stop_code"] == "live_observation_timeout"
    assert report["phase_b_executed"] is False
    summary = report["summary"]
    assert summary["completed_model_replies"] == summary["retries"] == 0
    assert summary["estimated_cost_usd"] == 0.003
    assert summary["input_tokens"] == 1000
    assert summary["billable_e2e_p95_ms"] == pytest.approx(29100)
    assert summary["model_p95_ms"] == pytest.approx(27900)
    sample = record["samples"][0]
    assert all(verdict == "not_run" for verdict in sample["checks"].values())
    assert sample["attempts"][0]["response_diagnostics"]["response_status"] == "completed"
    assert len(requests) == 2
    assert requests[0].extensions["timeout"]["read"] == 5
    assert requests[1].extensions["timeout"]["connect"] == 5
    assert requests[1].extensions["timeout"]["read"] == 28


@pytest.mark.parametrize(("model_seconds", "gate"), [(7, "pass"), (7.001, "fail")])
def test_observation_budget_does_not_move_inclusive_eight_second_gate(
    tmp_path, monkeypatch, model_seconds, gate
):
    report, _, _ = run_observed_case(tmp_path, monkeypatch, model_seconds=model_seconds)
    assert report["phase_a_status"] == "completed"
    assert report["measured_latency_gate"] == gate
    assert report["latency_threshold_ms"] == 8000
    assert report["summary"]["billable_e2e_p95_ms"] == (model_seconds + 1) * 1000


def test_read_timeout_beyond_observation_has_no_retry_and_unknown_cost(tmp_path, monkeypatch):
    report, record, requests = run_observed_case(tmp_path, monkeypatch, model_seconds=35)
    assert report["phase_a_status"] == "blocked"
    assert report["phase_a_stop_code"] == "live_read_timeout"
    assert report["phase_b_executed"] is False
    assert report["measured_latency_gate"] == "pending_evidence"
    summary = report["summary"]
    assert summary["live_calls"] == 1
    assert summary["retries"] == summary["completed_model_replies"] == 0
    assert summary["estimated_cost_usd"] is None
    assert 0 < report["budget_upper_bound_usd"] <= 0.20
    assert len(requests) == 2
    attempt = record["samples"][0]["attempts"][0]
    assert attempt["usage"] is None
    assert attempt["response_diagnostics"]["transport_error_code"] == "read_timeout"
    assert attempt["response_diagnostics"]["http_success"] is None


def test_late_complete_response_fails_closed_but_retains_observed_usage(tmp_path, monkeypatch):
    report, record, requests = run_observed_case(
        tmp_path, monkeypatch, model_seconds=31, honor_read_timeout=False
    )
    assert report["phase_a_status"] == "blocked"
    assert report["phase_a_stop_code"] == "live_observation_timeout"
    assert report["phase_b_executed"] is False
    summary = report["summary"]
    assert summary["live_calls"] == summary["paid_failures"] == 1
    assert summary["completed_model_replies"] == summary["retries"] == 0
    assert summary["system_safe_fallbacks"] == 1
    assert summary["input_tokens"] == 1000
    assert summary["estimated_cost_usd"] == 0.003
    assert report["measured_latency_gate"] == "fail"
    diagnostic = report["summary"]["latency_breakdown"]
    assert diagnostic["diagnostic_status"] == "not_an_operational_gate"
    assert diagnostic["components"]["production_equivalent_e2e_ms"]["p95_ms"] is None
    assert diagnostic["components"]["production_equivalent_e2e_ms"]["missing_n"] == 1
    assert diagnostic["components"]["input_count_ms"]["p95_ms"] == 1000
    attempt = record["samples"][0]["attempts"][0]
    assert attempt["response_diagnostics"]["response_status"] == "completed"
    assert attempt["response_diagnostics"]["total_tokens"] == 1100
    assert len(requests) == 2


def test_preflight_is_bounded_separately_and_submits_no_generation_on_timeout(
    tmp_path, monkeypatch
):
    report, _, requests = run_observed_case(
        tmp_path, monkeypatch, model_seconds=1, preflight_seconds=6
    )
    assert report["phase_a_stop_code"] == "live_preflight_failure"
    assert report["summary"]["live_calls"] == 0
    assert report["summary"]["retries"] == 0
    assert report["budget_upper_bound_usd"] == 0
    assert report["phase_b_executed"] is False
    assert len(requests) == 1
    assert requests[0].extensions["timeout"] == {
        "connect": 5.0,
        "read": 5.0,
        "write": 5.0,
        "pool": 5.0,
    }


def test_observation_timeout_preserves_evidence_when_generation_lease_has_expired(
    tmp_path, monkeypatch
):
    report, record, requests = run_observed_case(
        tmp_path,
        monkeypatch,
        model_seconds=31,
        honor_read_timeout=False,
        advance_utc=True,
    )
    assert report["phase_a_stop_code"] == "live_observation_timeout"
    assert report["phase_a_status"] == "blocked"
    assert report["phase_b_executed"] is False
    assert report["summary"]["completed_model_replies"] == 0
    assert report["summary"]["system_safe_fallbacks"] == 0
    assert report["summary"]["estimated_cost_usd"] == 0.003
    sample = record["samples"][0]
    assert sample["status"] == "failed"
    assert sample["reply_origin"] == "none"
    assert sample["attempts"][0]["response_diagnostics"]["response_status"] == "completed"
    assert sample["attempts"][0]["usage"]["input_tokens"] == 1000
    assert len(requests) == 2


def test_live_breakdown_reconciles_and_keeps_model_time_in_diagnostic(tmp_path, monkeypatch):
    from rj_studio_ai.conversation_context import ConversationContextBuilder
    from rj_studio_ai.delivery import OutboundDeliveryRunner
    from rj_studio_ai.evaluation.live_billing import BudgetLedger

    for target, method_name, seconds in (
        (persistence.SqliteConversationStore, "admit_generation", 0.01),
        (persistence.SqliteConversationStore, "claim_generation", 0.02),
        (persistence.SqliteConversationStore, "record_generation_metric", 0.03),
        (persistence.SqliteConversationStore, "complete_generation", 0.04),
        (BudgetLedger, "reserve", 0.05),
        (BudgetLedger, "settle", 0.07),
        (ConversationContextBuilder, "build", 0.04),
        (OutboundDeliveryRunner, "run_once", 0.06),
    ):
        method = getattr(target, method_name)

        def delayed(*args, _method=method, _seconds=seconds, **kwargs):
            result = _method(*args, **kwargs)
            live.perf_counter.advance(_seconds)
            return result

        monkeypatch.setattr(target, method_name, delayed)

    report, record, _ = run_observed_case(
        tmp_path, monkeypatch, model_seconds=12, validation_seconds=0.2, finalization_seconds=0.3
    )
    timing = record["samples"][0]["latency_breakdown"]
    for name, expected in {
        "admission_ms": 30,
        "input_count_ms": 1000,
        "budget_reservation_ms": 50,
        "model_request_ms": 12000,
        "decision_validation_ms": 200,
        "trusted_finalization_ms": 300,
        "persistence_ms": 70,
        "fake_outbound_ms": 60,
        "eval_bookkeeping_ms": 110,
        "unattributed_ms": 40,
        "observed_eval_e2e_ms": 13860,
        "production_equivalent_e2e_ms": 12700,
    }.items():
        assert timing[name] == pytest.approx(expected)
    assert report["summary"]["model_p95_ms"] == 12000
    assert report["summary"]["billable_e2e_p95_ms"] == pytest.approx(13860)
    assert report["measured_latency_gate"] == "fail"
    diagnostic = report["summary"]["latency_breakdown"]
    assert diagnostic["diagnostic_status"] == "not_an_operational_gate"
    assert diagnostic["components"]["production_equivalent_e2e_ms"]["p95_ms"] == pytest.approx(
        12700
    )
    assert diagnostic["components"]["input_count_ms"]["p95_ms"] == 1000
