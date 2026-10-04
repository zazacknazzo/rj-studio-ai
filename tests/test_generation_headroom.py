"""Allowlisted generation diagnostics and bounded headroom at provider seams."""

import pytest

from rj_studio_ai.evaluation.response_diagnostics import ResponseDiagnostics


@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
def test_incomplete_reason_is_observed_without_provider_content(reason):
    diagnostic = ResponseDiagnostics().observe(
        {
            "status": "incomplete",
            "incomplete_details": {"reason": reason, "reasoning": "hidden-private-reasoning"},
            "output": [{"text": "private-provider-output"}],
            "headers": {"Authorization": "private-credential"},
        }
    )
    assert diagnostic.incomplete_reason == reason
    assert diagnostic.incomplete_reason_present is True
    encoded = diagnostic.model_dump_json()
    assert all(
        value not in encoded
        for value in ("hidden-private-reasoning", "private-provider-output", "private-credential")
    )


def test_unknown_incomplete_reason_is_never_copied_from_provider():
    diagnostic = ResponseDiagnostics().observe(
        {"status": "incomplete", "incomplete_details": {"reason": "sensitive-provider-value"}}
    )
    assert diagnostic.incomplete_reason == "unrecognized"
    assert "sensitive-provider-value" not in diagnostic.model_dump_json()


def test_missing_reason_stays_unknown_and_historical_diagnostics_are_readable():
    diagnostic = ResponseDiagnostics().observe({"status": "incomplete"})
    assert diagnostic.incomplete_reason is None
    assert diagnostic.incomplete_reason_present is False
    historical = ResponseDiagnostics.model_validate({"response_status": "incomplete"})
    assert historical.incomplete_reason is None
    assert historical.incomplete_reason_present is None


def test_runtime_headroom_default_and_upper_bound_are_1024_without_changing_deadline(monkeypatch):
    from pydantic import ValidationError

    from rj_studio_ai.config import Settings
    from rj_studio_ai.deadline import ExecutionDeadline

    monkeypatch.delenv("ANTHROPIC_MAX_OUTPUT_TOKENS", raising=False)
    assert Settings(_env_file=None).anthropic_max_output_tokens == 1024
    assert (
        Settings(_env_file=None, anthropic_max_output_tokens=512).anthropic_max_output_tokens == 512
    )
    with pytest.raises(ValidationError):
        Settings(_env_file=None, anthropic_max_output_tokens=1025)
    deadline = ExecutionDeadline.start(clock=lambda: 0)
    assert deadline.remaining_budget() == 10


def test_live_request_and_reservation_share_1024_ceiling(tmp_path):
    import json

    import httpx
    from test_eval_openai_live import generator, response_payload

    from rj_studio_ai.conversation_context import ConversationContext
    from rj_studio_ai.domain import InboundMessage

    payloads = []

    def respond(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=response_payload())

    adapter, ledger = generator(tmp_path, respond)
    result = adapter.generate(
        InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
        context=ConversationContext((), ()),
        remaining_budget=29,
    )
    assert payloads[0]["max_output_tokens"] == 1024
    assert payloads[0]["reasoning"] == {"effort": "medium"}
    assert payloads[0]["service_tier"] == "default"
    assert result.metric.configuration.endswith("max_output_tokens=1024")
    journal = [json.loads(line) for line in (tmp_path / "budget.jsonl").read_text().splitlines()]
    assert journal[1]["output_bound"] == 1024
    ledger.close()


def test_anthropic_request_uses_same_ceiling_without_enabling_thinking():
    from test_anthropic_generation import RecordingClient

    from rj_studio_ai.conversation_context import ConversationContext
    from rj_studio_ai.domain import InboundMessage
    from rj_studio_ai.providers.anthropic import AnthropicReplyGenerator, LLMPriceTable

    client = RecordingClient()
    adapter = AnthropicReplyGenerator(
        api_key="synthetic-value",
        model="claude-sonnet-5",
        max_output_tokens=1024,
        pricing=LLMPriceTable(
            input_microusd_per_million=3_000_000, output_microusd_per_million=15_000_000
        ),
        client=client,
    )
    adapter.generate(
        InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
        context=ConversationContext((), ()),
        remaining_budget=9,
    )
    assert client.messages.calls[0]["max_tokens"] == 1024
    assert client.messages.calls[0]["thinking"] == {"type": "disabled"}
