"""Offline-only CLI. Importing/executing this module never constructs production settings."""

import argparse
import json
import subprocess
from pathlib import Path

from rj_studio_ai.evaluation.records import RunRecord
from rj_studio_ai.evaluation.reporting import aggregate, compare, report
from rj_studio_ai.evaluation.runner import dry_run
from rj_studio_ai.evaluation.suite import load_suite


def _write(path, data):
    # Exclusive creation prevents overwriting evidence or a credential file by mistake.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _load_record(path, suite):
    record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
    if (
        record.fingerprints.suite != suite.digest
        or record.fingerprints.knowledge != suite.knowledge_digest
        or record.contracts != tuple(case.contract for case in suite.cases)
    ):
        raise ValueError("eval_record_suite_mismatch")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline V1 eval evidence tools")
    parser.add_argument("--suite", type=Path, default=Path("docs/evals/V1"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-suite")
    run = commands.add_parser("dry-run")
    run.add_argument("--repetitions", type=int, default=1)
    run.add_argument("--output", type=Path, required=True)
    for name in ("validate-record", "report"):
        command = commands.add_parser(name)
        command.add_argument("record", type=Path)
    aggregate_command = commands.add_parser("aggregate")
    aggregate_command.add_argument("records", type=Path, nargs="+")
    compare_command = commands.add_parser("compare")
    compare_command.add_argument("first", type=Path)
    compare_command.add_argument("second", type=Path)
    compare_command.add_argument("--blind-sheet", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        suite = load_suite(args.suite)
        if args.command == "validate-suite":
            result = {
                "suite_id": "v1",
                "total_cases": len(suite.cases),
                "categories": sorted({tag for case in suite.cases for tag in case.categories}),
                "suite_hash": suite.digest,
            }
        elif args.command == "dry-run":
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            record = dry_run(suite, repetitions=args.repetitions, revision=revision)
            _write(args.output, record.model_dump(mode="json"))
            result = report(record)
        elif args.command in {"validate-record", "report"}:
            record = _load_record(args.record, suite)
            result = (
                {"valid": True, "run_id": record.run_id}
                if args.command == "validate-record"
                else report(record)
            )
        elif args.command == "aggregate":
            summary = aggregate([_load_record(path, suite) for path in args.records])
            result = summary.model_dump(mode="json")
        else:
            result, sheet = compare(
                _load_record(args.first, suite), _load_record(args.second, suite)
            )
            _write(args.blind_sheet, sheet)
    except Exception:
        # Pydantic/YAML exceptions can echo offending input. Never print them.
        print(json.dumps({"error": "eval_validation_or_execution_failed"}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
