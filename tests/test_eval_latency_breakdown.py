import pytest

from rj_studio_ai.evaluation.latency import LatencyBreakdown, LatencyRecorder


def breakdown_payload():
    return {
        "admission_ms": 10.0,
        "input_count_ms": 1000.0,
        "budget_reservation_ms": 20.0,
        "model_request_ms": 12000.0,
        "decision_validation_ms": 30.0,
        "trusted_finalization_ms": 40.0,
        "persistence_ms": 50.0,
        "fake_outbound_ms": 60.0,
        "eval_bookkeeping_ms": 50.0,
        "unattributed_ms": 90.0,
        "observed_eval_e2e_ms": 13350.0,
        "production_equivalent_e2e_ms": 12280.0,
    }


def test_diagnostic_excludes_only_count_reservation_and_measured_eval_bookkeeping():
    value = LatencyBreakdown.model_validate(breakdown_payload())
    assert value.observed_eval_e2e_ms == 13350
    assert value.production_equivalent_e2e_ms == 12280
    assert value.production_equivalent_e2e_ms > value.model_request_ms > 8000


@pytest.mark.parametrize("field", list(breakdown_payload()))
def test_negative_component_or_total_is_rejected(field):
    payload = {**breakdown_payload(), field: -1.0}
    with pytest.raises(ValueError):
        LatencyBreakdown.model_validate(payload)


def test_missing_measurement_stays_unknown_and_cannot_produce_diagnostic():
    payload = {**breakdown_payload(), "input_count_ms": None}
    with pytest.raises(ValueError, match="latency_diagnostic_missing_evidence"):
        LatencyBreakdown.model_validate(payload)
    payload["production_equivalent_e2e_ms"] = None
    payload["unattributed_ms"] = 1090.0
    value = LatencyBreakdown.model_validate(payload)
    assert value.input_count_ms is None
    assert value.production_equivalent_e2e_ms is None


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("unattributed_ms", 100.0, "latency_components_do_not_reconcile"),
        ("production_equivalent_e2e_ms", 280.0, "latency_diagnostic_mismatch"),
    ],
)
def test_component_sum_and_diagnostic_cannot_omit_model_time(field, value, code):
    payload = {**breakdown_payload(), field: value}
    with pytest.raises(ValueError, match=code):
        LatencyBreakdown.model_validate(payload)


@pytest.mark.parametrize("field", ["reply_text", "reasoning", "api_key", "customer_message"])
def test_latency_allowlist_rejects_content_and_secret_fields(field):
    with pytest.raises(ValueError):
        LatencyBreakdown.model_validate({**breakdown_payload(), field: "synthetic-value"})


def test_nested_eval_bookkeeping_does_not_double_count_or_zero_unobserved_stages():
    now = [0.0]
    recorder = LatencyRecorder(clock=lambda: now[0])
    with recorder.measure("decision_validation_ms"):
        now[0] += 0.02
        with recorder.measure("eval_bookkeeping_ms"):
            now[0] += 0.01
    result = recorder.finish(30.0)
    assert result.decision_validation_ms == pytest.approx(20)
    assert result.eval_bookkeeping_ms == pytest.approx(10)
    assert result.unattributed_ms == 0
    assert result.model_request_ms is None
    assert result.production_equivalent_e2e_ms is None


def test_recorder_rejects_regressing_clock():
    now = [1.0]
    recorder = LatencyRecorder(clock=lambda: now[0])
    with (
        pytest.raises(ValueError, match="latency_clock_regressed"),
        recorder.measure("model_request_ms"),
    ):
        now[0] = 0.0
