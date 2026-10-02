import json

import httpx
import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.openai_live import OpenAIEvalGenerator
from rj_studio_ai.evaluation.suite import fixture_decision
from rj_studio_ai.generation import GenerationFailure


def response_payload(**overrides):
    return {
        "model": "gpt-6.1-sol",
        "service_tier": "default",
        "status": "completed",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
            "output_tokens_details": {"reasoning_tokens": 40},
        },
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": fixture_decision().model_dump_json()}],
            }
        ],
        **overrides,
    }


def generator(tmp_path, transport):
    ledger = BudgetLedger(tmp_path / "budget.jsonl", LivePricing.load())
    client = httpx.Client(transport=httpx.MockTransport(transport))
    return OpenAIEvalGenerator(
        api_key="synthetic-value", client=client, ledger=ledger, phase="A"
    ), ledger


def test_live_adapter_is_standard_stateless_and_accounts_real_usage(tmp_path):
    requests = []

    def transport(request):
        requests.append(request)
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        return httpx.Response(200, json=response_payload())

    adapter, ledger = generator(tmp_path, transport)
    result = adapter.generate(
        InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
        context=ConversationContext((), ()),
        remaining_budget=9,
    )
    payload = json.loads(requests[-1].content)
    assert payload["model"] == "gpt-6.1-sol"
    assert payload["service_tier"] == "default"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 200
    assert payload["text"]["format"]["strict"] is True
    assert result.trusted_reply is None
    assert adapter.attempts[0].usage.reasoning_tokens == 40
    assert str(ledger.upper_bound_usd) == "0.00277"
    ledger.close()


@pytest.mark.parametrize(
    "payload",
    [
        response_payload(usage=None),
        response_payload(status="incomplete"),
        response_payload(service_tier="priority"),
    ],
)
def test_bad_usage_truncation_or_wrong_tier_stops_without_hidden_retry(tmp_path, payload):
    calls = []

    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        calls.append(request)
        return httpx.Response(200, json=payload)

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    assert len(calls) == 1
    assert adapter.stop_code is not None
    assert len(adapter.attempts) == 1
    ledger.close()
