import asyncio
import json
from datetime import date
from time import monotonic
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.conversation_context import ConversationContext, ConversationTurn
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import GenerationFailure, GenerationTimeout, TransientGenerationError
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import SqliteConversationStore
from rj_studio_ai.providers.anthropic import AnthropicReplyGenerator, LLMPriceTable
from rj_studio_ai.salon_knowledge import SalonKnowledgeFact


class RecordingMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=_decision_json())],
            model="claude-sonnet-5",
            usage=SimpleNamespace(input_tokens=120, output_tokens=15),
        )


class RecordingClient:
    def __init__(self) -> None:
        self.messages = RecordingMessages()


class RaisingMessages:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    def create(self, **kwargs: object) -> object:
        del kwargs
        self.calls += 1
        raise self._error


class RaisingClient:
    def __init__(self, error: Exception) -> None:
        self.messages = RaisingMessages(error)


class BlockingMessages:
    def __init__(self) -> None:
        self.cancelled = False

    async def create(self, **kwargs: object) -> object:
        del kwargs
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class BlockingClient:
    def __init__(self) -> None:
        self.messages = BlockingMessages()


class BlockingCloseClient:
    def __init__(self) -> None:
        self.messages = RecordingMessages()
        self.close_cancelled = False

    async def close(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.close_cancelled = True
            raise


class BlockingRequestAndCloseClient:
    def __init__(self) -> None:
        self.messages = BlockingMessages()
        self.close_called = False

    async def close(self) -> None:
        self.close_called = True
        await asyncio.Event().wait()


class FailingCloseClient:
    def __init__(self) -> None:
        self.messages = RecordingMessages()

    async def close(self) -> None:
        raise RuntimeError("cleanup failed")


class RetryMessages(RecordingMessages):
    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise anthropic.APITimeoutError(_request())
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=_decision_json("Resposta"))],
            model="claude-sonnet-5",
            usage=SimpleNamespace(input_tokens=20, output_tokens=5),
        )


class RetryClient:
    def __init__(self) -> None:
        self.messages = RetryMessages()


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _message() -> InboundMessage:
    return InboundMessage(
        provider="test-provider",
        provider_message_id="message-1",
        customer_address="customer-1",
        recipient_address="studio",
        body="Olá",
    )


def _decision_json(reply_text: str = "Olá! Como posso ajudar?") -> str:
    return json.dumps(
        {
            "intents": ["greeting"],
            "reply_text": reply_text,
            "uncertainty": "low",
            "knowledge_refs": [],
            "critical_claims": [],
            "handoff": False,
            "handoff_reason": None,
        }
    )


def _generator(client: object) -> AnthropicReplyGenerator:
    return AnthropicReplyGenerator(
        api_key="test-key",
        model="claude-sonnet-5",
        max_output_tokens=200,
        pricing=LLMPriceTable(
            input_microusd_per_million=3_000_000,
            output_microusd_per_million=15_000_000,
        ),
        client=client,  # type: ignore[arg-type]
    )


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.test/messages")


def _response(status_code: int) -> httpx2.Response:
    return httpx2.Response(status_code, request=_request())


def test_anthropic_adapter_uses_structured_output_without_thinking() -> None:
    client = RecordingClient()
    generator = AnthropicReplyGenerator(
        api_key="test-key",
        model="claude-sonnet-5",
        max_output_tokens=200,
        pricing=LLMPriceTable(
            input_microusd_per_million=3_000_000, output_microusd_per_million=15_000_000
        ),
        client=client,
    )

    result = generator.generate(_message(), remaining_budget=4.5)

    assert result.reply_body == "Olá! Como posso ajudar?"
    assert result.metric.provider == "anthropic"
    assert result.metric.model == "claude-sonnet-5"
    assert result.metric.input_tokens == 120
    assert result.metric.output_tokens == 15
    assert result.metric.total_tokens == 135
    assert result.metric.estimated_cost_microusd == 585
    assert result.metric.configuration == "thinking=disabled;format=json_schema;max_tokens=200"
    assert result.metric.outcome == "success"
    assert result.metric.error_code is None
    assert len(client.messages.calls) == 1
    request = client.messages.calls[0]
    assert request["model"] == "claude-sonnet-5"
    assert request["max_tokens"] == 200
    assert request["thinking"] == {"type": "disabled"}
    schema = request["output_config"]["format"]["schema"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "intents",
        "reply_text",
        "uncertainty",
        "knowledge_refs",
        "critical_claims",
        "handoff",
        "handoff_reason",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert request["system"] == (
        "Responda em português brasileiro, de forma breve. "
        "Não invente fatos do salão; peça esclarecimento quando faltar contexto. "
        "Produza somente a decisão estruturada, sem raciocínio textual."
    )
    assert request["messages"] == [{"role": "user", "content": "Olá"}]
    assert request["timeout"] == 4.5


def test_anthropic_adapter_receives_prepared_history_knowledge_and_one_current_message() -> None:
    client = RecordingClient()
    context = ConversationContext(
        history=(
            ConversationTurn(role="customer", body="Quero corte"),
            ConversationTurn(role="ai_attendant", body="Claro, posso ajudar."),
        ),
        history_may_be_incomplete=True,
        knowledge=(
            SalonKnowledgeFact(
                id="service-corte",
                category="service",
                topic="corte",
                status="approved",
                fact_type="operational_commercial",
                statement="Serviço sintético de corte.",
                source="synthetic fixture",
                reviewed_at=date(2026, 9, 20),
                approved_by="RJ Studio operator",
            ),
        ),
    )

    _generator(client).generate(_message(), context=context, remaining_budget=4.5)

    request = client.messages.calls[0]
    assert request["messages"] == [
        {"role": "user", "content": "Quero corte"},
        {"role": "assistant", "content": "Claro, posso ajudar."},
        {"role": "user", "content": "Olá"},
    ]
    system = str(request["system"])
    assert "histórico anterior pode estar incompleto" in system
    assert "Approved Salon Knowledge:" in system
    assert "service-corte" in system
    assert "customer-1" not in system
    assert "message-1" not in system
    assert "studio" not in system


def test_missing_anthropic_runtime_configuration_is_not_ready(tmp_path) -> None:
    database_path = tmp_path / "missing-key.db"
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            llm_provider="anthropic",
            twilio_validate_signature=False,
        )
    )

    with TestClient(app) as client:
        readiness = client.get("/ready")
        webhook = client.post(
            "/webhooks/twilio",
            data={"MessageSid": "message-1", "From": "customer", "To": "studio", "Body": "Oi"},
        )

    assert readiness.status_code == 503
    assert readiness.json()["checks"]["configuration"] == "failed"
    assert webhook.status_code == 503
    assert (
        SqliteConversationStore(database_path).get_generation(
            provider="twilio", provider_message_id="message-1"
        )
        is None
    )


def test_anthropic_adapter_does_not_start_when_budget_cannot_cover_a_real_request() -> None:
    client = RecordingClient()

    with pytest.raises(GenerationTimeout, match="provider_timeout"):
        _generator(client).generate(_message(), remaining_budget=0.99)

    assert client.messages.calls == []


@pytest.mark.parametrize(
    ("error", "error_type", "error_code"),
    [
        (
            anthropic.APITimeoutError(_request()),
            GenerationTimeout,
            "provider_timeout",
        ),
        (
            anthropic.APIConnectionError(message="connection", request=_request()),
            TransientGenerationError,
            "provider_connection",
        ),
        (
            anthropic.RateLimitError("rate", response=_response(429), body={}),
            TransientGenerationError,
            "provider_rate_limit",
        ),
        (
            anthropic.InternalServerError("internal", response=_response(500), body={}),
            TransientGenerationError,
            "provider_unavailable",
        ),
        (
            anthropic.AuthenticationError("auth", response=_response(401), body={}),
            GenerationFailure,
            "provider_authentication",
        ),
        (
            anthropic.BadRequestError("invalid", response=_response(400), body={}),
            GenerationFailure,
            "provider_request",
        ),
        (
            anthropic.APIResponseValidationError(_response(200), body={}),
            TransientGenerationError,
            "invalid_provider_response",
        ),
    ],
)
def test_anthropic_adapter_classifies_provider_failures(
    error: Exception,
    error_type: type[GenerationFailure],
    error_code: str,
) -> None:
    client = RaisingClient(error)

    with pytest.raises(error_type) as raised:
        _generator(client).generate(_message(), remaining_budget=4.5)

    assert raised.value.error_code == error_code
    assert raised.value.metric is not None
    assert raised.value.metric.outcome == "failure"
    assert raised.value.metric.error_code == error_code
    assert client.messages.calls == 1


def test_anthropic_adapter_rejects_malformed_structured_output_with_available_usage() -> None:
    client = RecordingClient()
    client.messages.create = lambda **_: SimpleNamespace(
        content=[SimpleNamespace(type="text", text="not-json")],
        model="claude-sonnet-5",
        usage=SimpleNamespace(input_tokens=40, output_tokens=4),
    )

    with pytest.raises(TransientGenerationError) as raised:
        _generator(client).generate(_message(), remaining_budget=4.5)

    assert raised.value.error_code == "invalid_structured_decision"
    assert raised.value.metric is not None
    assert raised.value.metric.input_tokens == 40
    assert raised.value.metric.output_tokens == 4


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "intents": ["greeting"],
            "reply_text": "Oi",
            "uncertainty": "low",
            "knowledge_refs": [],
            "critical_claims": [],
            "handoff": False,
        },
        {
            "intents": ["unknown"],
            "reply_text": "Oi",
            "uncertainty": "low",
            "knowledge_refs": [],
            "critical_claims": [],
            "handoff": False,
            "handoff_reason": None,
        },
    ],
)
def test_anthropic_adapter_rejects_invalid_decision_schema(payload: dict[str, object]) -> None:
    client = RecordingClient()
    client.messages.create = lambda **_: SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        model="claude-sonnet-5",
        usage=SimpleNamespace(input_tokens=40, output_tokens=4),
    )

    with pytest.raises(TransientGenerationError, match="invalid_structured_decision"):
        _generator(client).generate(_message(), remaining_budget=4.5)


def test_anthropic_adapter_rejects_a_draft_knowledge_reference(tmp_path) -> None:
    context = ConversationContext(
        history=(),
        knowledge=(
            SalonKnowledgeFact(
                id="draft-corte",
                category="service",
                topic="corte",
                status="draft",
                fact_type="operational_commercial",
                statement="Rascunho sintético.",
                source="synthetic fixture",
                reviewed_at=date(2026, 9, 20),
            ),
        ),
    )
    payload = json.loads(_decision_json())
    payload["knowledge_refs"] = ["draft-corte"]
    client = RecordingClient()
    client.messages.create = lambda **_: SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        model="claude-sonnet-5",
        usage=SimpleNamespace(input_tokens=40, output_tokens=4),
    )

    with pytest.raises(TransientGenerationError, match="invalid_structured_decision"):
        _generator(client).generate(_message(), context=context, remaining_budget=4.5)


def test_anthropic_adapter_allows_missing_optional_usage() -> None:
    client = RecordingClient()
    client.messages.create = lambda **_: SimpleNamespace(
        content=[SimpleNamespace(type="text", text=_decision_json("Oi"))],
        model="claude-sonnet-5",
        usage=SimpleNamespace(),
    )

    result = _generator(client).generate(_message(), remaining_budget=4.5)

    assert result.metric.input_tokens is None
    assert result.metric.output_tokens is None
    assert result.metric.estimated_cost_microusd is None


def test_anthropic_adapter_cancels_an_inflight_request_at_the_total_budget() -> None:
    client = BlockingClient()
    started_at = monotonic()

    with pytest.raises(GenerationTimeout, match="provider_timeout"):
        _generator(client).generate(_message(), remaining_budget=1.0)

    assert monotonic() - started_at < 1.5
    assert client.messages.cancelled


def test_anthropic_adapter_bounds_client_cleanup_by_the_total_budget() -> None:
    client = BlockingCloseClient()
    started_at = monotonic()

    with pytest.raises(GenerationTimeout, match="provider_timeout"):
        _generator(client).generate(_message(), remaining_budget=1.0)

    assert monotonic() - started_at < 1.5
    assert client.close_cancelled


def test_anthropic_adapter_skips_cleanup_after_request_timeout() -> None:
    client = BlockingRequestAndCloseClient()
    started_at = monotonic()

    with pytest.raises(GenerationTimeout, match="provider_timeout"):
        _generator(client).generate(_message(), remaining_budget=1.0)

    assert monotonic() - started_at < 1.5
    assert client.messages.cancelled
    assert not client.close_called


def test_anthropic_adapter_does_not_mask_a_successful_reply_with_cleanup_error() -> None:
    result = _generator(FailingCloseClient()).generate(_message(), remaining_budget=1.0)

    assert result.reply_body == "Olá! Como posso ajudar?"


def test_invalid_sdk_response_retries_safely_and_records_failure_metrics(tmp_path) -> None:
    database_path = tmp_path / "invalid-sdk-response.db"
    generator = _generator(
        RaisingClient(anthropic.APIResponseValidationError(_response(200), body={}))
    )
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta segura",
            twilio_validate_signature=False,
        ),
        generator=generator,
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            data={"MessageSid": "message-1", "From": "customer", "To": "studio", "Body": "Oi"},
        )

    assert response.status_code == 200
    assert "Resposta segura" in response.text
    lifecycle = SqliteConversationStore(database_path).get_generation(
        provider="twilio", provider_message_id="message-1"
    )
    assert lifecycle is not None
    assert [
        (metric.outcome, metric.error_code)
        for metric in SqliteConversationStore(database_path).get_generation_metrics(
            inbound_message_id=lifecycle.inbound_message_id
        )
    ] == [("failure", "invalid_provider_response"), ("failure", "invalid_provider_response")]


def test_anthropic_retry_uses_the_remaining_webhook_deadline(tmp_path) -> None:
    clock = FakeClock()
    client = RetryClient()
    generator = AnthropicReplyGenerator(
        api_key="test-key",
        model="claude-sonnet-5",
        max_output_tokens=200,
        pricing=LLMPriceTable(
            input_microusd_per_million=3_000_000,
            output_microusd_per_million=15_000_000,
        ),
        client=client,
        clock=clock,
    )
    store = SqliteConversationStore(tmp_path / "deadline.db")
    store.initialize()
    responder = MessageResponder(
        store=store,
        generator=generator,
        safe_failure_reply="Resposta segura",
        sleeper=clock.advance,
    )
    deadline = ExecutionDeadline.start(clock=clock)
    clock.advance(2.0)

    reply = responder.handle(_message(), deadline=deadline)

    assert reply.body == "Resposta"
    assert [call["timeout"] for call in client.messages.calls] == [7.0, 6.9]


def test_invalid_structured_decision_retries_safely_then_replays_safe_reply(tmp_path) -> None:
    database_path = tmp_path / "invalid-decision.db"
    client = RecordingClient()
    client.messages.create = lambda **_: SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"intents": ["greeting"]}')],
        model="claude-sonnet-5",
        usage=SimpleNamespace(input_tokens=40, output_tokens=4),
    )
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta segura",
            twilio_validate_signature=False,
        ),
        generator=_generator(client),
    )

    with TestClient(app) as test_client:
        first = test_client.post(
            "/webhooks/twilio",
            data={"MessageSid": "message-1", "From": "customer", "To": "studio", "Body": "Oi"},
        )
        replay = test_client.post(
            "/webhooks/twilio",
            data={
                "MessageSid": "message-1",
                "From": "customer",
                "To": "studio",
                "Body": "Alterado",
            },
        )

    assert first.text == replay.text
    assert "<Message>Resposta segura</Message>" in first.text
    lifecycle = SqliteConversationStore(database_path).get_generation(
        provider="twilio", provider_message_id="message-1"
    )
    assert lifecycle is not None
    assert lifecycle.reply_body == "Resposta segura"
    assert [
        (metric.outcome, metric.error_code)
        for metric in SqliteConversationStore(database_path).get_generation_metrics(
            inbound_message_id=lifecycle.inbound_message_id
        )
    ] == [
        ("failure", "invalid_structured_decision"),
        ("failure", "invalid_structured_decision"),
    ]


def test_anthropic_adapter_rejects_output_cap_above_the_v1_contract() -> None:
    with pytest.raises(ValueError, match="between 1 and 200"):
        AnthropicReplyGenerator(
            api_key="test-key",
            model="claude-sonnet-5",
            max_output_tokens=201,
            pricing=LLMPriceTable(
                input_microusd_per_million=3_000_000,
                output_microusd_per_million=15_000_000,
            ),
            client=RecordingClient(),
        )


def test_valid_multi_intent_decision_survives_webhook_and_replay(tmp_path) -> None:
    database_path = tmp_path / "valid-multi-intent.db"
    client = RecordingClient()
    payload = json.loads(
        _decision_json("Posso confirmar os valores com a equipe. Qual período você prefere?")
    )
    payload["intents"] = ["price", "appointment_interest"]

    def create(**kwargs: object) -> object:
        client.messages.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
            model="claude-sonnet-5",
            usage=SimpleNamespace(input_tokens=40, output_tokens=16),
        )

    client.messages.create = create
    app = create_app(
        Settings(
            _env_file=None,
            database_path=database_path,
            automatic_reply="Resposta segura",
            twilio_validate_signature=False,
        ),
        generator=_generator(client),
    )
    form = {
        "MessageSid": "message-1",
        "From": "customer",
        "To": "studio",
        "Body": "Quanto custa progressiva e tem horário sexta?",
    }

    with TestClient(app) as test_client:
        first = test_client.post("/webhooks/twilio", data=form)
        replay = test_client.post("/webhooks/twilio", data=form)

    assert first.status_code == replay.status_code == 200
    assert first.text == replay.text
    assert "Qual período você prefere?" in first.text
    assert "disponível" not in first.text
    assert len(client.messages.calls) == 1
    lifecycle = SqliteConversationStore(database_path).get_generation(
        provider="twilio", provider_message_id="message-1"
    )
    assert lifecycle is not None
    assert (
        lifecycle.reply_body
        == "Posso confirmar os valores com a equipe. Qual período você prefere?"
    )
