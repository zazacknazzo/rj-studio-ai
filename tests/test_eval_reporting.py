from copy import deepcopy

import pytest
from test_eval_records import record_data

from rj_studio_ai.evaluation.records import RunRecord
from rj_studio_ai.evaluation.reporting import aggregate, compare, report


def test_report_names_numerator_denominator_and_run_count():
    rendered = report(RunRecord.model_validate(record_data()))
    assert rendered["run_count"] == 1
    assert rendered["critical_failures"] == "0/1 (0.00%)"
    assert rendered["metrics"]["grounding"] == "1/1 (100.00%)"
    assert rendered["naturalness"] == "pending_human_review"


def test_aggregation_recomputes_population_and_rejects_duplicate_run_ids():
    first = RunRecord.model_validate(record_data())
    data = deepcopy(record_data())
    data["run_id"] = "second-run"
    second = RunRecord.model_validate(data)
    summary = aggregate([first, second])
    assert summary.run_count == 2
    assert summary.completed_replies == 2
    assert summary.critical_failures.denominator == 2
    with pytest.raises(ValueError):
        aggregate([first, first])


def test_paired_comparison_is_equivalent_and_sheet_is_blind():
    first = RunRecord.model_validate(record_data())
    data = deepcopy(record_data())
    data["run_id"] = "challenger-run"
    data["configuration"].update(provider="challenger", model="challenger-model")
    second = RunRecord.model_validate(data)
    comparison, sheet = compare(first, second)
    assert sheet["rubric_version"] == "livia-naturalness-v1"
    assert len(sheet["pairs"]) == 1
    assert sheet["pairs"][0]["preference"] == "pending"
    assert comparison["mapping"]
    assert "challenger" not in str(sheet)
    data["fingerprints"]["knowledge"] = "c" * 64
    with pytest.raises(ValueError):
        compare(first, RunRecord.model_validate(data))
