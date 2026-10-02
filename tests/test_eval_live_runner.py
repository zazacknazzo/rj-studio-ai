from pathlib import Path

import httpx

from rj_studio_ai.evaluation.live import execute_live
from rj_studio_ai.evaluation.suite import load_suite


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
    assert result["phase_a_status"] == "blocked"
    assert (tmp_path / "run" / "human-review.md").exists()
