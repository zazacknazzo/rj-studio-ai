from copy import deepcopy

import pytest
from pydantic import ValidationError

from rj_studio_ai.evaluation.records import RunRecord, summarize


def record_data():
    return {
        "schema_version": 1,
        "run_id": "synthetic-run",
        "suite_id": "v1",
        "mode": "deterministic",
        "status": "completed",
        "created_at": "2026-10-02T12:00:00Z",
        "revision": "631782a",
        "configuration": {
            "provider": "deterministic",
            "model": "fixture-proposals-v1",
            "max_output_tokens": 200,
            "thinking": "disabled",
            "structured_output": True,
            "context_max_messages": 12,
            "context_token_budget": 4000,
        },
        "fingerprints": {key: "a" * 64 for key in ("suite", "knowledge", "prompt")},
        "repetitions": 1,
        "total_cases": 1,
        "contracts": [
            {
                "case_id": "synthetic-case",
                "turns": 1,
                "checks": {
                    "grounded": {"metric": "grounding", "critical": True},
                },
            }
        ],
        "pricing": None,
        "samples": [
            {
                "case_id": "synthetic-case",
                "repetition": 1,
                "turn": 1,
                "status": "completed",
                "reply_hash": "b" * 64,
                "checks": {"grounded": "pass"},
                "attempts": [
                    {
                        "number": 1,
                        "outcome": "success",
                        "billable": False,
                        "input_tokens": None,
                        "output_tokens": None,
                        "latency_ms": 2,
                    }
                ],
                "e2e_latency_ms": 4,
            }
        ],
        "summary": {
            "run_count": 1,
            "completed_replies": 1,
            "billable_retries": 0,
            "token_consuming_failures": 0,
            "unknown_billing_attempts": 0,
            "input_tokens": None,
            "output_tokens": None,
            "model_p50_ms": 2,
            "model_p95_ms": 2,
            "e2e_p50_ms": 4,
            "e2e_p95_ms": 4,
            "billable_e2e_p50_ms": None,
            "billable_e2e_p95_ms": None,
            "estimated_cost_usd": None,
            "cost_per_1000_replies_usd": None,
            "critical_failures": {"numerator": 0, "denominator": 1},
            "metrics": {"grounding": {"numerator": 1, "denominator": 1}},
        },
    }


def test_versioned_valid_record_and_no_pricing_means_no_cost_claim():
    record = RunRecord.model_validate(record_data())
    assert record.summary.completed_replies == 1
    assert record.summary.critical_failures.denominator == 1
    assert record.summary.cost_per_1000_replies_usd is None
    assert record.gates() == {"safety": "pass", "latency": "pending_live", "cost": "pending_live"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data["summary"]["critical_failures"].pop("denominator"),
        lambda data: data["samples"][0]["checks"].update(grounded="fail"),
        lambda data: data["samples"][0]["checks"].clear(),
        lambda data: data["samples"][0]["attempts"][0].update(latency_ms=-1),
        lambda data: data.update(customer_message="Real customer data"),
        lambda data: data["configuration"].update(api_key="sk-ant-secret-example"),
    ],
)
def test_invalid_or_underreported_record_is_rejected(mutation):
    data = deepcopy(record_data())
    mutation(data)
    with pytest.raises((ValidationError, ValueError)):
        RunRecord.model_validate(data)


def test_billable_retry_and_paid_error_cost_do_not_inflate_completed_replies():
    data = record_data()
    data["pricing"] = {
        "version": "synthetic-v1",
        "status": "synthetic",
        "provider": "deterministic",
        "model": "fixture-proposals-v1",
        "source": "synthetic-test-only",
        "input_usd_per_million": "1",
        "output_usd_per_million": "2",
    }
    data["samples"][0]["attempts"] = [
        {
            "number": 1,
            "outcome": "failure",
            "billable": True,
            "input_tokens": 1000,
            "output_tokens": 100,
            "latency_ms": 10,
            "error_code": "synthetic-timeout",
        },
        {
            "number": 2,
            "outcome": "success",
            "billable": True,
            "input_tokens": 1000,
            "output_tokens": 100,
            "latency_ms": 20,
        },
    ]
    summary = summarize(data["samples"], data["contracts"], data["pricing"])
    data["summary"] = summary.model_dump(mode="json")
    record = RunRecord.model_validate(data)
    assert record.summary.estimated_cost_usd == pytest.approx(0.0024)
    assert record.summary.cost_per_1000_replies_usd == pytest.approx(2.4)
    assert record.summary.completed_replies == 1
    assert record.summary.billable_retries == 1
    assert record.summary.token_consuming_failures == 1
    assert record.summary.model_p50_ms == 15
    assert record.summary.model_p95_ms == 19.5


def test_failed_paid_execution_remains_in_cost_latency_population():
    data = record_data()
    data["pricing"] = {
        "version": "synthetic-v1",
        "status": "synthetic",
        "provider": "deterministic",
        "model": "fixture-proposals-v1",
        "source": "synthetic-test-only",
        "input_usd_per_million": "1",
        "output_usd_per_million": "2",
    }
    failed = deepcopy(data["samples"][0])
    failed.update(repetition=2, status="failed", reply_hash=None, e2e_latency_ms=20000)
    failed["attempts"] = [
        {
            "number": 1,
            "outcome": "failure",
            "billable": True,
            "input_tokens": 1000,
            "output_tokens": 0,
            "latency_ms": 19000,
            "error_code": "synthetic-error",
        }
    ]
    failed["checks"] = {"grounded": "fail"}
    data["samples"].append(failed)
    data["repetitions"] = 2
    data["summary"] = summarize(data["samples"], data["contracts"], data["pricing"]).model_dump()
    record = RunRecord.model_validate(data)
    assert record.summary.completed_replies == 1
    assert record.summary.estimated_cost_usd == 0.001
    assert record.summary.cost_per_1000_replies_usd == 1
    assert record.summary.e2e_p95_ms == pytest.approx(19000.2)
    assert record.summary.critical_failures.numerator == 1
    assert record.summary.critical_failures.denominator == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "AC" + "a" * 32),
        ("model", "sk-ant-example-credential"),
        ("model", "5511999998888"),
        ("model", "sk-" + "a" * 48),
        ("model", "sk-svcacct-" + "a" * 48),
        ("model", "2026-10-02T5511999998888"),
    ],
)
def test_forbidden_value_in_allowed_metadata_field_is_rejected(field, value):
    data = record_data()
    data["configuration"][field] = value
    with pytest.raises(ValueError):
        RunRecord.model_validate(data)


@pytest.mark.parametrize("field", ["latency_ms", "e2e_latency_ms"])
def test_boolean_latency_is_not_a_numeric_measurement(field):
    data = record_data()
    if field == "latency_ms":
        data["samples"][0]["attempts"][0][field] = True
    else:
        data["samples"][0][field] = True
    with pytest.raises(ValueError):
        RunRecord.model_validate(data)


def test_live_import_cannot_use_deterministic_configuration_to_approve_gate():
    data = record_data()
    data["mode"] = "live_import"
    with pytest.raises(ValueError):
        RunRecord.model_validate(data)


def test_live_completed_reply_without_attempt_evidence_is_rejected():
    data = record_data()
    data["mode"] = "live_import"
    data["configuration"].update(provider="synthetic-import", model="synthetic-model")
    data["samples"][0]["attempts"] = []
    data["summary"] = summarize(data["samples"], data["contracts"]).model_dump()
    with pytest.raises(ValueError):
        RunRecord.model_validate(data)


def test_suppression_cannot_dilute_billable_end_to_end_gate_population():
    data = record_data()
    data.update(mode="live_import", latency_scope="inbound_persistence_to_provider_acceptance")
    data["configuration"].update(provider="synthetic-import", model="synthetic-model")
    data["repetitions"] = 20
    paid = data["samples"][0]
    paid.update(e2e_latency_ms=10000)
    paid["attempts"][0].update(billable=True, input_tokens=100, output_tokens=10, latency_ms=10000)
    for number in range(2, 21):
        suppressed = deepcopy(paid)
        suppressed.update(
            repetition=number, status="suppressed", reply_hash=None, attempts=[], e2e_latency_ms=0
        )
        data["samples"].append(suppressed)
    data["summary"] = summarize(data["samples"], data["contracts"]).model_dump()
    record = RunRecord.model_validate(data)
    assert record.summary.e2e_p95_ms == pytest.approx(500)
    assert record.summary.billable_e2e_p95_ms == 10000
    assert record.gates()["latency"] == "fail"
