"""Product-owner approved low default; explicit medium remains available in eval."""

import json
from pathlib import Path

import httpx
import pytest
from test_commercial_live_retest import decision
from test_eval_openai_live import response_payload

from rj_studio_ai.evaluation.live import run_live_phase
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.suite import load_suite


@pytest.mark.parametrize("override,expected", [(None, "low"), ("medium", "medium")])
def test_live_default_and_explicit_override_preserve_frozen_configuration(
    tmp_path, override, expected
):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        return httpx.Response(
            200,
            json=response_payload(
                output=[
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": decision(0).model_dump_json()}],
                    }
                ]
            ),
        )

    ledger = BudgetLedger(tmp_path / "spend.jsonl", LivePricing.load())
    options = {} if override is None else {"reasoning_effort": override}
    try:
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            record, packet = run_live_phase(
                load_suite(Path("docs/evals/V1")),
                [("grounding-divergent-price", 1)],
                "A",
                api_key="synthetic-value",
                output=tmp_path,
                revision="85499cb",
                ledger=ledger,
                client=client,
                **options,
            )
        assert record.configuration["reasoning_effort"] == expected
        assert record.configuration["model"] == "gpt-6.1-sol"
        assert record.configuration["service_tier"] == "default"
        assert record.configuration["max_output_tokens"] == 1024
        assert record.configuration["observation_deadline_seconds"] == 30
        assert record.configuration["finalization_margin_seconds"] == 1
        assert record.configuration["http_connect_timeout_seconds"] == 5
        assert record.configuration["input_count_timeout_seconds"] == 5
        assert all(payload["reasoning"] == {"effort": expected} for payload in requests)
        assert len(record.samples[0].attempts) == 1
        assert record.samples[0].attempts[0].usage is not None
        assert record.samples[0].checks == {"trusted_facts": "pass", "handoff_policy": "pass"}
        assert packet[0]["response"] == "O corte custa R$ 120,00."
    finally:
        ledger.close()
