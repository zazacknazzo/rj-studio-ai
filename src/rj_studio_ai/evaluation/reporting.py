"""Population aggregation and paired blind review preparation; no model execution."""

import secrets
from uuid import uuid4

from rj_studio_ai.evaluation.records import RunRecord, Summary, summarize


def _equivalent(first, second, *, comparison=False):
    left = first.configuration.model_dump()
    right = second.configuration.model_dump()
    if comparison:
        for key in ("provider", "model"):
            left.pop(key)
            right.pop(key)
    if (
        first.fingerprints != second.fingerprints
        or first.contracts != second.contracts
        or first.revision != second.revision
        or left != right
        or first.mode != second.mode
        or first.latency_scope != second.latency_scope
    ):
        raise ValueError("eval_inequivalent_runs")


def aggregate(runs: list[RunRecord]) -> Summary:
    if not runs or len({run.run_id for run in runs}) != len(runs):
        raise ValueError("eval_missing_or_duplicate_run")
    first = runs[0]
    for run in runs[1:]:
        _equivalent(first, run)
        if run.pricing != first.pricing:
            raise ValueError("eval_inequivalent_pricing")
    return summarize(
        [sample for run in runs for sample in run.samples],
        first.contracts,
        first.pricing,
        run_count=len(runs),
    )


def _ratio(ratio):
    percent = f"{100 * ratio.numerator / ratio.denominator:.2f}%" if ratio.denominator else "n/a"
    return f"{ratio.numerator}/{ratio.denominator} ({percent})"


def report(run: RunRecord) -> dict:
    summary = run.summary.model_dump(mode="json")
    summary.update(
        run_id=run.run_id,
        mode=run.mode,
        status=run.status,
        total_cases=run.total_cases,
        repetitions=run.repetitions,
        configuration=run.configuration.model_dump(),
        critical_failures=_ratio(run.summary.critical_failures),
        metrics={name: _ratio(ratio) for name, ratio in run.summary.metrics.items()},
        naturalness=run.naturalness_status,
        gates=run.gates(),
        latency_scope=run.latency_scope,
    )
    return summary


def compare(first: RunRecord, second: RunRecord) -> tuple[dict, dict]:
    _equivalent(first, second, comparison=True)
    if first.repetitions != second.repetitions or first.run_id == second.run_id:
        raise ValueError("eval_invalid_pairing")
    index = {(s.case_id, s.repetition, s.turn): s for s in second.samples}
    pairs, mapping = [], {}
    for left in first.samples:
        key = (left.case_id, left.repetition, left.turn)
        right = index[key]
        swap = secrets.randbelow(2) == 1
        a, b = (right, left) if swap else (left, right)
        pair_id = uuid4().hex
        pairs.append(
            {
                "pair_id": pair_id,
                "case_id": left.case_id,
                "repetition": left.repetition,
                "turn": left.turn,
                "answer_a_hash": a.reply_hash,
                "answer_b_hash": b.reply_hash,
                "scores_a": {
                    name: None
                    for name in (
                        "warmth",
                        "whatsapp_clarity",
                        "persona_stability",
                        "contextual_fit",
                    )
                },
                "scores_b": {
                    name: None
                    for name in (
                        "warmth",
                        "whatsapp_clarity",
                        "persona_stability",
                        "contextual_fit",
                    )
                },
                "preference": "pending",
            }
        )
        mapping[pair_id] = {
            "A": second.run_id if swap else first.run_id,
            "B": first.run_id if swap else second.run_id,
        }
    return (
        {"first": report(first), "second": report(second), "mapping": mapping},
        {
            "schema_version": 1,
            "rubric_version": "livia-naturalness-v1",
            "status": "pending_human_review",
            "pairs": pairs,
        },
    )
