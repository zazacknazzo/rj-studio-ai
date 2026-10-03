import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_eval_records import record_data

from rj_studio_ai.evaluation.__main__ import main
from rj_studio_ai.evaluation.records import RunRecord, percentile, summarize

SUITE = Path(__file__).parents[1] / "docs/evals/V1"


def test_offline_cli_validates_runs_reports_and_compares(tmp_path, capsys):
    assert main(["--suite", str(SUITE), "validate-suite"]) == 0
    assert json.loads(capsys.readouterr().out)["total_cases"] == 53
    run_path = tmp_path / "run.json"
    assert main(["--suite", str(SUITE), "dry-run", "--output", str(run_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["gates"]["cost"] == "pending_live"
    assert main(["--suite", str(SUITE), "validate-record", str(run_path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert main(["--suite", str(SUITE), "report", str(run_path)]) == 0
    assert json.loads(capsys.readouterr().out)["run_count"] == 1
    second = json.loads(run_path.read_text())
    second["run_id"] = "second-run"
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(second))
    sheet = tmp_path / "blind.json"
    assert (
        main(
            [
                "--suite",
                str(SUITE),
                "compare",
                str(run_path),
                str(second_path),
                "--blind-sheet",
                str(sheet),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert json.loads(sheet.read_text())["status"] == "pending_human_review"
    assert main(["--suite", str(SUITE), "aggregate", str(run_path), str(second_path)]) == 0
    assert json.loads(capsys.readouterr().out)["run_count"] == 2
    # Never overwrite existing evidence.
    before = run_path.read_bytes()
    assert main(["--suite", str(SUITE), "dry-run", "--output", str(run_path)]) == 1
    capsys.readouterr()
    assert run_path.read_bytes() == before


def test_cli_never_echoes_invalid_sensitive_input(tmp_path, capsys):
    path = tmp_path / "bad.json"
    data = record_data()
    data["configuration"]["model"] = "sk-ant-credential-example"
    path.write_text(json.dumps(data))
    assert main(["--suite", str(SUITE), "validate-record", str(path)]) == 1
    output = capsys.readouterr()
    assert "sk-ant" not in output.out + output.err
    assert "eval_validation_or_execution_failed" in output.out


def test_linear_percentiles_and_empty_population():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([10, 20, 30, 40], 0.95) == pytest.approx(38.5)
    assert percentile([], 0.95) is None


def test_unknown_billing_or_usage_blocks_cost_claim():
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
    data["samples"][0]["attempts"][0]["billable"] = None
    summary = summarize(data["samples"], data["contracts"], data["pricing"])
    assert summary.unknown_billing_attempts == 1
    assert summary.estimated_cost_usd is None
    data["samples"][0]["attempts"][0]["billable"] = True
    summary = summarize(data["samples"], data["contracts"], data["pricing"])
    assert summary.cost_per_1000_replies_usd is None


def test_recomputed_critical_failure_fails_safety_gate():
    data = record_data()
    data["samples"][0]["checks"]["grounded"] = "fail"
    data["summary"] = summarize(data["samples"], data["contracts"]).model_dump()
    assert RunRecord.model_validate(data).gates()["safety"] == "fail"


def test_failed_record_without_completed_reply_has_no_cost_denominator():
    data = record_data()
    sample = data["samples"][0]
    sample.update(status="failed", reply_hash=None)
    summary = summarize(data["samples"], data["contracts"])
    assert summary.completed_replies == 0
    assert summary.cost_per_1000_replies_usd is None


def test_record_rejects_duplicate_sample_and_missing_repetition():
    data = record_data()
    data["samples"].append(deepcopy(data["samples"][0]))
    with pytest.raises(ValueError):
        RunRecord.model_validate(data)
    data = record_data()
    data["repetitions"] = 2
    with pytest.raises(ValueError):
        RunRecord.model_validate(data)
