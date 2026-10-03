import json
from decimal import Decimal

import httpx
import pytest

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.live_billing import BudgetLedger, LivePricing
from rj_studio_ai.evaluation.openai_live import OpenAIEvalGenerator
from rj_studio_ai.evaluation.response_diagnostics import ResponseDiagnostics
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
    assert payload["max_output_tokens"] == 512
    assert result.metric.configuration == "effort=medium;tier=default;max_output_tokens=512"
    reservations = [
        json.loads(line) for line in (tmp_path / "budget.jsonl").read_text().splitlines()
    ]
    assert reservations[1]["output_bound"] == 512
    assert payload["text"]["format"]["strict"] is True
    assert result.trusted_reply is None
    assert adapter.attempts[0].usage.reasoning_tokens == 40
    diagnostics = adapter.attempts[0].response_diagnostics
    assert diagnostics.response_status == "completed"
    assert diagnostics.usage_present is True
    assert diagnostics.usage_validation_error_code is None
    assert diagnostics.http_success is True
    assert diagnostics.total_tokens == 1100
    assert all(
        getattr(diagnostics, name + "_present")
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
        )
    )
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


def test_count_failure_submits_no_paid_request(tmp_path):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {"message": "synthetic error"}})

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure, match="input_count_failed"):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    assert len(calls) == 1
    assert calls[0].url.path.endswith("input_tokens")
    assert adapter.attempts == []
    assert ledger.upper_bound_usd == 0
    ledger.close()


def test_ambiguous_timeout_has_unknown_billing_and_blocks_another_submission(tmp_path):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        raise httpx.ReadTimeout("synthetic-timeout")

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    assert adapter.attempts[0].usage is None
    assert adapter.attempts[0].billable is None
    assert adapter.stop_code == "live_read_timeout"
    diagnostics = adapter.attempts[0].response_diagnostics
    assert diagnostics.http_success is None
    assert diagnostics.usage_present is None
    assert diagnostics.transport_error_code == "read_timeout"
    assert ledger.upper_bound_usd > 0
    with pytest.raises(ValueError, match="unresolved_submission"):
        ledger.reserve("A", input_bound=1, output_bound=1)
    ledger.close()


@pytest.mark.parametrize("omit_field", [False, True])
def test_absent_usage_is_distinguished_from_transport_error_and_keeps_reservation(
    tmp_path, omit_field
):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        data = response_payload(usage=None)
        if omit_field:
            data.pop("usage")
        return httpx.Response(200, json=data)

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure, match="live_usage_absent"):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    attempt = adapter.attempts[0]
    assert attempt.usage is None
    assert attempt.response_diagnostics.response_status == "completed"
    assert attempt.response_diagnostics.usage_present is False
    assert attempt.response_diagnostics.http_success is True
    assert attempt.response_diagnostics.usage_validation_error_code == "usage_absent"
    journal = [json.loads(line) for line in (tmp_path / "budget.jsonl").read_text().splitlines()]
    assert ledger.upper_bound_usd == Decimal(journal[1]["reserved_usd"])
    assert journal[-1] == {"kind": "settle", "usage": None}
    with pytest.raises(ValueError, match="unresolved_submission"):
        ledger.reserve("A", input_bound=1000, output_bound=512)
    ledger.close()


@pytest.mark.parametrize(
    ("usage", "code"),
    [
        ([], "usage_invalid_shape"),
        (
            {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
            "usage_cache_breakdown_missing",
        ),
        ({**response_payload()["usage"], "total_tokens": 1200}, "usage_total_mismatch"),
        (
            {
                **response_payload()["usage"],
                "input_tokens_details": {
                    "cached_tokens": 900,
                    "cache_write_tokens": 300,
                },
            },
            "usage_input_breakdown",
        ),
    ],
)
def test_present_invalid_usage_retains_presence_and_specific_rejection(tmp_path, usage, code):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        return httpx.Response(200, json=response_payload(usage=usage))

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure, match="live_" + code):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    diagnostics = adapter.attempts[0].response_diagnostics
    assert diagnostics.usage_present is True
    assert diagnostics.usage_validation_error_code == code
    assert adapter.attempts[0].usage is None
    assert ledger.blocked is True
    ledger.close()


@pytest.mark.parametrize("status", ["incomplete", "failed"])
@pytest.mark.parametrize("usage_present", [False, True])
def test_noncompleted_response_keeps_status_and_never_releases_gate(
    tmp_path, status, usage_present
):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        return httpx.Response(
            200,
            json=response_payload(
                status=status,
                usage=response_payload()["usage"] if usage_present else None,
            ),
        )

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    diagnostics = adapter.attempts[0].response_diagnostics
    assert diagnostics.response_status == status
    assert diagnostics.usage_present is usage_present
    assert diagnostics.usage_validation_error_code == (None if usage_present else "usage_absent")
    assert adapter.decisions == [None]
    assert adapter.stop_code is not None
    ledger.close()


def test_diagnostics_project_only_safe_fields_and_do_not_retain_output_or_errors():
    data = response_payload(
        id="raw-operational-id",
        output="private-output-sentinel",
        reasoning="private-reasoning-sentinel",
        authorization="Bearer sk-forbidden",
    )
    diagnostics = ResponseDiagnostics(http_success=True, http_status_code=200).observe(data)
    serialized = diagnostics.model_dump_json()
    for forbidden in [
        "private-output",
        "private-reasoning",
        "Bearer",
        "sk-forbidden",
        "raw-operational",
    ]:
        assert forbidden not in serialized
    assert diagnostics.input_tokens == 1000
    assert diagnostics.reasoning_tokens == 40
    with pytest.raises(ValueError):
        ResponseDiagnostics.model_validate({**diagnostics.model_dump(), "output": "forbidden"})


@pytest.mark.parametrize("failure", ["http", "json", "transport"])
def test_nonusage_failure_is_not_misclassified_as_absent_api_usage(tmp_path, failure):
    def transport(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(200, json={"input_tokens": 1000})
        if failure == "http":
            return httpx.Response(503, text="private-output-sentinel")
        if failure == "json":
            return httpx.Response(200, text="private-output-sentinel")
        raise httpx.ConnectError("Bearer sk-forbidden private-transport-sentinel")

    adapter, ledger = generator(tmp_path, transport)
    with pytest.raises(GenerationFailure):
        adapter.generate(
            InboundMessage("eval", "one", "synthetic", "synthetic", "Oi"),
            context=ConversationContext((), ()),
            remaining_budget=9,
        )
    attempt = adapter.attempts[0]
    assert (
        attempt.error_code
        == {
            "http": "live_http_failure",
            "json": "live_response_json_invalid",
            "transport": "live_transport_error",
        }[failure]
    )
    assert attempt.response_diagnostics.usage_present is None
    assert attempt.response_diagnostics.usage_validation_error_code is None
    for forbidden in ["private-output", "private-transport", "Bearer", "sk-forbidden"]:
        assert forbidden not in attempt.model_dump_json()
    ledger.close()
