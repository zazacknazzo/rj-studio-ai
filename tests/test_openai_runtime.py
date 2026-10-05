import asyncio
import json
from dataclasses import asdict
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.conversation_context import (
    ConversationContextBuilder,
    ConversationContextLimits,
)
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.evaluation.suite import fixture_decision
from rj_studio_ai.generation import FixedReplyGenerator, GenerationFailure, GenerationTimeout
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.processing import ProcessingExecutor, ProcessingRunner
from rj_studio_ai.providers.openai import OpenAIReplyGenerator
from rj_studio_ai.runtime import generator_from_settings
from rj_studio_ai.salon_knowledge import SalonKnowledgeFact, SalonKnowledgeRepository


def test_openai_runtime_selection_and_approved_defaults():
    settings = Settings(_env_file=None, llm_provider="openai", openai_api_key="synthetic-key")
    generator = generator_from_settings(settings)
    assert generator.is_configured()
    assert settings.openai_model == "gpt-6.1-sol"
    assert settings.openai_reasoning_effort == "low"
    assert settings.openai_max_output_tokens == 1024


def test_safe_default_and_existing_anthropic_selection_are_preserved():
    assert isinstance(generator_from_settings(Settings(_env_file=None)), FixedReplyGenerator)
    assert (
        generator_from_settings(Settings(_env_file=None, llm_provider="anthropic")).provider
        == "anthropic"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_provider": "invalid"},
        {"openai_model": "unsupported"},
        {"openai_reasoning_effort": "invalid"},
        {"openai_max_output_tokens": 1025},
    ],
)
def test_invalid_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_explicit_openai_configuration_and_missing_key():
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_reasoning_effort="medium",
        openai_max_output_tokens=512,
    )
    assert settings.openai_reasoning_effort == "medium"
    assert settings.openai_max_output_tokens == 512
    assert not generator_from_settings(settings).is_configured()


def message(body="Oi", identifier="first"):
    return InboundMessage("synthetic", identifier, "synthetic-customer", "synthetic-channel", body)


def response_data(decision=None):
    return {
        "model": "gpt-6.1-sol",
        "service_tier": "default",
        "status": "completed",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 30},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
        "output": [
            {"type": "reasoning", "summary": [{"text": "PRIVATE_REASONING"}]},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            decision
                            or fixture_decision(
                                surface="agentic",
                                intents=["greeting"],
                                reply_parts=[
                                    {
                                        "kind": "conversation",
                                        "purpose": "social",
                                        "text": "Oi! Como posso te ajudar?",
                                        "targets": [],
                                    }
                                ],
                            ).model_dump(mode="json")
                        ),
                    }
                ],
            },
        ],
    }


def generator_for(handler):
    return OpenAIReplyGenerator(
        api_key="synthetic-private-key",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_runtime_request_and_safe_usage_are_shared_with_eval():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_data())

    result = generator_for(handler).generate(message(), remaining_budget=4)
    assert result.trusted_reply is None
    assert result.metric.cached_input_tokens == 10
    assert result.metric.cache_write_tokens == 30
    assert result.metric.reasoning_tokens == 5
    assert result.metric.response_status == "completed"
    assert "PRIVATE_REASONING" not in str(result)
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/responses"
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_output_tokens"] == 1024
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert requests[0].extensions["timeout"]["read"] == 4


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "provider_authentication"),
        (403, "provider_authentication"),
        (429, "provider_rate_limit"),
        (500, "provider_unavailable"),
        (400, "provider_request"),
    ],
)
def test_http_failure_is_safe_and_transport_has_no_retry(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="synthetic-private-key PRIVATE_REASONING")

    with pytest.raises(GenerationFailure) as error:
        generator_for(handler).generate(message(), remaining_budget=2)
    assert error.value.error_code == code
    assert "synthetic-private-key" not in str(error.value)
    assert "PRIVATE_REASONING" not in str(error.value.metric)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("update", "code"),
    [
        (
            {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}},
            "provider_incomplete",
        ),
        ({"usage": None}, "usage_absent"),
        ({"output": []}, "invalid_structured_decision"),
        (
            {"output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]},
            "invalid_structured_decision",
        ),
        ({"model": "unsupported"}, "invalid_provider_response"),
    ],
)
def test_invalid_generation_fails_without_a_trusted_reply(update, code):
    data = response_data()
    data.update(update)
    with pytest.raises(GenerationFailure) as error:
        generator_for(lambda _: httpx.Response(200, json=data)).generate(
            message(), remaining_budget=2
        )
    assert error.value.error_code == code
    if data.get("status") == "incomplete":
        assert error.value.metric.incomplete_reason == "max_output_tokens"
        assert error.value.metric.input_tokens == 100


def test_processing_executor_persists_safe_metadata_and_restart_replays_once(tmp_path):
    store = SqliteConversationStore(tmp_path / "runtime.db")
    store.initialize()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response_data())

    generator = generator_for(handler)
    executor = ProcessingExecutor(
        runner=ProcessingRunner(
            store=store,
            responder=MessageResponder(
                store=store,
                generator=generator,
                safe_failure_reply="safe",
                completion_delivery_state=DeliveryState.PENDING,
            ),
        ),
        poll_interval_seconds=0.1,
        concurrency=1,
    )
    admitted = store.admit_generation(message())
    result = executor.run_once()
    assert result.reply_body == "Oi! Como posso te ajudar?"
    metric = store.get_generation_metrics(inbound_message_id=admitted.inbound_message_id)[0]
    assert metric.cached_input_tokens == 10
    assert metric.reasoning_tokens == 5
    assert metric.response_status == "completed"
    assert "PRIVATE_REASONING" not in json.dumps(asdict(metric))
    assert (
        store.get_delivery_for_inbound(admitted.inbound_message_id).state == DeliveryState.PENDING
    )
    restarted = SqliteConversationStore(tmp_path / "runtime.db")
    assert restarted.admit_generation(message()).reply_body == result.reply_body
    assert len(calls) == 1


def test_request_is_cancelled_at_supplied_budget_without_retries():
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(2)
        return httpx.Response(200, json=response_data())

    with pytest.raises(GenerationTimeout, match="provider_timeout"):
        generator_for(handler).generate(message(), remaining_budget=1)
    assert len(calls) == 1


def price_fact():
    return SalonKnowledgeFact(
        id="price-corte",
        category="price",
        topic="corte",
        status="approved",
        fact_type="operational_commercial",
        statement="O corte custa R$ 120,00.",
        source="synthetic fixture",
        reviewed_at=date(2026, 10, 5),
        approved_by="synthetic-operator",
    )


def pipeline(tmp_path, proposal, body):
    store = SqliteConversationStore(tmp_path / "pipeline.db")
    store.initialize()
    facts = tmp_path / "synthetic-knowledge.yaml"
    facts.write_text(json.dumps({"version": 1, "facts": [price_fact().model_dump(mode="json")]}))
    knowledge = SalonKnowledgeRepository(facts)
    knowledge.load()
    responder = MessageResponder(
        store=store,
        generator=generator_for(
            lambda _: httpx.Response(200, json=response_data(proposal.model_dump(mode="json")))
        ),
        safe_failure_reply="safe",
        context_builder=ConversationContextBuilder(
            store=store, salon_knowledge=knowledge, limits=ConversationContextLimits()
        ),
        completion_delivery_state=DeliveryState.PENDING,
    )
    inbound = message(body)
    admitted = store.admit_generation(inbound)
    result = ProcessingExecutor(
        runner=ProcessingRunner(store=store, responder=responder),
        poll_interval_seconds=0.1,
        concurrency=1,
    ).run_once()
    return store, admitted, result


def test_openai_model_cannot_change_trusted_price_or_send_free_factual_text(tmp_path):
    proposal = fixture_decision(
        surface="agentic",
        intents=["price"],
        reply_text="O corte custa R$ 1,00.",
        knowledge_refs=["price-corte"],
        reply_parts=[{"kind": "fact", "knowledge_ref": "price-corte"}],
    )
    store, admitted, result = pipeline(tmp_path, proposal, "Quanto custa o corte?")
    assert "R$ 120,00" in result.reply_body
    assert "R$ 1,00" not in result.reply_body
    assert store.get_delivery_for_inbound(admitted.inbound_message_id).body == result.reply_body


@pytest.mark.parametrize(
    "body", ["Quero falar com uma pessoa", "Meu couro cabeludo está ardendo depois da química"]
)
def test_openai_cannot_bypass_handoff_even_with_false_proposal(tmp_path, body):
    proposal = fixture_decision(
        surface="agentic",
        intents=["other"],
        reply_parts=[
            {
                "kind": "conversation",
                "purpose": "social",
                "text": "Oi! Como posso ajudar?",
                "targets": [],
            }
        ],
        handoff=False,
    )
    store, admitted, result = pipeline(tmp_path, proposal, body)
    assert store.list_active_handoffs()
    assert result.reply_body
    later = store.admit_generation(message("Oi de novo", "later"))
    assert later.state.value == "suppressed"
    assert store.get_delivery_for_inbound(later.inbound_message_id) is None


def test_openai_cannot_promise_booking_or_availability(tmp_path):
    proposal = fixture_decision(
        surface="agentic",
        intents=["appointment_interest"],
        appointment_preferences={"desired_service": "corte", "preferred_day": "sexta"},
        reply_parts=[
            {
                "kind": "conversation",
                "purpose": "social",
                "text": "Agendamento confirmado para sexta, temos vaga!",
                "targets": [],
            }
        ],
    )
    store, admitted, result = pipeline(tmp_path, proposal, "Quero corte sexta")
    assert "confirmado" not in result.reply_body
    assert "temos vaga" not in result.reply_body
    assert store.get_delivery_for_inbound(admitted.inbound_message_id)


def test_invalid_ref_rejected_at_provider_boundary():
    proposal = fixture_decision(
        intents=["price"],
        knowledge_refs=["not-approved"],
        reply_parts=[{"kind": "fact", "knowledge_ref": "not-approved"}],
    )
    with pytest.raises(GenerationFailure, match="invalid_structured_decision"):
        generator_for(
            lambda _: httpx.Response(200, json=response_data(proposal.model_dump(mode="json")))
        ).generate(message(), remaining_budget=2)


def test_missing_runtime_key_fails_readiness_without_calls(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "missing.db",
            llm_provider="openai",
            openai_api_key="",
            twilio_validate_signature=False,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["configuration"] == "failed"


@pytest.mark.parametrize(
    "data", [{"status": {}}, {"status": "completed", "incomplete_details": {"reason": {}}}]
)
def test_malformed_status_or_reason_cannot_leak_raw_exception(data):
    payload = response_data()
    payload.update(data)
    generator = generator_for(lambda _: httpx.Response(200, json=payload))
    try:
        result = generator.generate(message(), remaining_budget=2)
    except GenerationFailure as error:
        assert error.metric.response_status == "unrecognized"
    else:
        assert result.metric.incomplete_reason == "unrecognized"
