from pathlib import Path

from rj_studio_ai.evaluation.runner import dry_run
from rj_studio_ai.evaluation.suite import load_suite

SUITE = Path(__file__).parents[1] / "docs/evals/V1"


def test_offline_runner_uses_real_policy_seams_and_explicit_repetitions(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("network must never be used in offline evals")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-never-be-read")
    suite = load_suite(SUITE)
    record = dry_run(suite, repetitions=2, revision="631782a")
    assert record.total_cases == 52
    assert record.repetitions == 2
    assert len(record.samples) > 104  # Multi-turn episodes stay a single case.
    assert record.configuration.provider == "deterministic"
    assert record.summary.critical_failures.numerator == 0
    assert record.summary.critical_failures.denominator > 0
    assert all(ratio.numerator == ratio.denominator for ratio in record.summary.metrics.values())
    assert record.summary.completed_replies < len(record.samples)  # Durable suppression.
    assert record.gates()["latency"] == "pending_live"
    serialized = record.model_dump_json()
    assert "customer_message" not in serialized
    assert "reply_text" not in serialized
    assert "should-never-be-read" not in serialized
