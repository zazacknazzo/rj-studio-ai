from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Condition, Event, Lock
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.config import Settings
from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.domain import AIReply, InboundMessage
from rj_studio_ai.generation import GeneratedReply, GenerationMetric, TransientGenerationError
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import (
    GenerationMetricRecord,
    GenerationState,
    RecentContextHistory,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import (
    ProviderWebhookRequest,
    ProviderWebhookResponse,
    WhatsAppProvider,
)
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self._lock = Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.value

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.value += seconds

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


class FormProvider(WhatsAppProvider):
    def __init__(self, *, receive_delay: FakeClock | None = None) -> None:
        self._receive_delay = receive_delay
        self._received_count = 0
        self._received = Condition()

    def receive(self, webhook: ProviderWebhookRequest) -> InboundMessage:
        if self._receive_delay is not None:
            self._receive_delay.advance(8.95)
        form = parse_qs(webhook.body.decode("utf-8"), strict_parsing=True)
        with self._received:
            self._received_count += 1
            self._received.notify_all()
        return InboundMessage(
            provider="test-provider",
            provider_message_id=form["MessageSid"][0],
            customer_address=form["From"][0],
            recipient_address="studio",
            body=form["Body"][0],
        )

    def reply(self, reply: AIReply) -> ProviderWebhookResponse:
        return ProviderWebhookResponse(body=reply.body, media_type="text/plain")

    def is_configured(self) -> bool:
        return True

    def wait_for_received(self, count: int) -> bool:
        with self._received:
            return self._received.wait_for(lambda: self._received_count >= count, timeout=1.0)


class RecordingGenerator:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.budgets: list[float] = []
        self._lock = Lock()

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        with self._lock:
            self.calls.append(message.body)
            self.budgets.append(remaining_budget)
        return GeneratedReply.from_reply_text(f"reply:{message.body}")

    def is_configured(self) -> bool:
        return True


class ContextRecordingGenerator(RecordingGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.contexts: list[ConversationContext] = []

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        assert isinstance(context, ConversationContext)
        self.contexts.append(context)
        return super().generate(message, context=context, remaining_budget=remaining_budget)


class MetricGenerator(RecordingGenerator):
    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        super().generate(message, context=context, remaining_budget=remaining_budget)
        return GeneratedReply.from_reply_text(
            f"reply:{message.body}",
            metric=GenerationMetric(
                provider="anthropic",
                model="claude-sonnet-5",
                configuration="thinking=disabled;format=json_schema;max_tokens=200",
                latency_ms=120,
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
                estimated_cost_microusd=675,
                outcome="success",
                error_code=None,
            ),
        )


class FailingMetricGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        del message, remaining_budget
        self.calls += 1
        raise TransientGenerationError(
            "provider_timeout",
            GenerationMetric(
                provider="anthropic",
                model="claude-sonnet-5",
                configuration="thinking=disabled;format=json_schema;max_tokens=200",
                latency_ms=1_000,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                estimated_cost_microusd=None,
                outcome="failure",
                error_code=None,
            ),
        )

    def is_configured(self) -> bool:
        return True


class OrderedBlockingGenerator(RecordingGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.first_started = Event()
        self.release_first = Event()
        self.second_started = Event()

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        with self._lock:
            self.calls.append(message.body)
            self.budgets.append(remaining_budget)
        if message.body == "first":
            self.first_started.set()
            if not self.release_first.wait(timeout=2.0):
                raise RuntimeError("first generation was not released")
        else:
            self.second_started.set()
        return GeneratedReply.from_reply_text(f"reply:{message.body}")


class ParallelGenerator(RecordingGenerator):
    def __init__(self) -> None:
        super().__init__()
        self._barrier = Barrier(2)

    def generate(
        self,
        message: InboundMessage,
        *,
        context: object | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        with self._lock:
            self.calls.append(message.body)
            self.budgets.append(remaining_budget)
        self._barrier.wait(timeout=1.0)
        return GeneratedReply.from_reply_text(f"reply:{message.body}")


class FirstRenderConsumesDeadlineProvider(FormProvider):
    def __init__(self, clock: FakeClock) -> None:
        super().__init__()
        self._clock = clock
        self.reply_attempts = 0

    def reply(self, reply: AIReply) -> ProviderWebhookResponse:
        self.reply_attempts += 1
        if self.reply_attempts == 1:
            self._clock.advance(10.0)
        return super().reply(reply)


class ContextDelayStore(SqliteConversationStore):
    def __init__(self, database_path: Path, clock: FakeClock) -> None:
        super().__init__(database_path)
        self._clock = clock
        self.context_lock_timeouts: list[float | None] = []

    def load_recent_context_history(
        self,
        *,
        inbound_message_id: int,
        maximum_age: timedelta,
        maximum_messages: int,
        lock_timeout: float | None = None,
    ) -> RecentContextHistory:
        self.context_lock_timeouts.append(lock_timeout)
        self._clock.advance(2.0)
        return super().load_recent_context_history(
            inbound_message_id=inbound_message_id,
            maximum_age=maximum_age,
            maximum_messages=maximum_messages,
            lock_timeout=lock_timeout,
        )


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        automatic_reply="safe reply",
        twilio_validate_signature=False,
    )


def _form(message_id: str, customer: str, body: str) -> dict[str, str]:
    return {"MessageSid": message_id, "From": customer, "Body": body}


def test_webhook_uses_canonical_history_once_and_replay_does_not_rebuild_or_generate(
    tmp_path: Path,
) -> None:
    generator = ContextRecordingGenerator()
    app = create_app(
        _settings(tmp_path / "context-webhook.db"),
        provider=FormProvider(),
        generator=generator,
    )

    with TestClient(app) as client:
        first = client.post("/webhooks/twilio", data=_form("first", "customer-1", "Quero corte"))
        second = client.post(
            "/webhooks/twilio", data=_form("second", "customer-1", "E para amanhã?")
        )
        replay = client.post(
            "/webhooks/twilio",
            data=_form("second", "customer-1", "Corpo alterado no retry"),
        )

    assert [response.status_code for response in (first, second, replay)] == [200, 200, 200]
    assert [response.text for response in (second, replay)] == [
        "reply:E para amanhã?",
        "reply:E para amanhã?",
    ]
    assert generator.calls == ["Quero corte", "E para amanhã?"]
    assert [(turn.role, turn.body) for turn in generator.contexts[1].history] == [
        ("customer", "Quero corte"),
        ("ai_attendant", "reply:Quero corte"),
    ]
    assert generator.contexts[1].knowledge == ()


def test_context_loading_consumes_the_existing_webhook_deadline(tmp_path: Path) -> None:
    clock = FakeClock()
    store = ContextDelayStore(tmp_path / "context-deadline.db", clock)
    generator = RecordingGenerator()
    app = create_app(
        _settings(tmp_path / "context-deadline.db"),
        provider=FormProvider(),
        store=store,
        generator=generator,
        monotonic_clock=clock,
        sleeper=clock.sleep,
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=_form("message-1", "customer-1", "Oi"))

    assert response.status_code == 200
    assert store.context_lock_timeouts == [pytest.approx(9.0)]
    assert generator.budgets == [pytest.approx(7.0)]


def test_webhook_selects_approved_salon_knowledge_for_the_current_message(tmp_path: Path) -> None:
    knowledge_path = tmp_path / "knowledge.yaml"
    knowledge_path.write_text(
        """
version: 1
facts:
  - id: service-corte
    category: service
    topic: corte
    status: approved
    fact_type: operational_commercial
    statement: Serviço sintético de corte.
    source: synthetic fixture
    reviewed_at: 2026-09-20
    approved_by: RJ Studio operator
""".lstrip(),
        encoding="utf-8",
    )
    generator = ContextRecordingGenerator()
    app = create_app(
        _settings(tmp_path / "knowledge-webhook.db"),
        provider=FormProvider(),
        generator=generator,
        salon_knowledge=SalonKnowledgeRepository(knowledge_path),
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio", data=_form("message-1", "customer-1", "Quero corte")
        )

    assert response.status_code == 200
    assert [fact.id for fact in generator.contexts[0].knowledge] == ["service-corte"]


def test_oversized_current_message_gets_the_safe_reply_without_llm_generation(
    tmp_path: Path,
) -> None:
    generator = RecordingGenerator()
    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "oversized-current.db",
            automatic_reply="safe reply",
            llm_input_token_budget=500,
            twilio_validate_signature=False,
        ),
        provider=FormProvider(),
        generator=generator,
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            data=_form("message-1", "customer-1", "x" * 200),
        )

    assert response.status_code == 200
    assert response.text == "safe reply"
    assert generator.calls == []


def test_two_concurrent_messages_in_one_conversation_generate_in_order(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ordered-webhook.db"
    provider = FormProvider()
    generator = OrderedBlockingGenerator()
    app = create_app(
        _settings(database_path),
        provider=provider,
        generator=generator,
    )

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            client.post,
            "/webhooks/twilio",
            data=_form("message-1", "customer-1", "first"),
        )
        assert generator.first_started.wait(timeout=1.0)
        second = executor.submit(
            client.post,
            "/webhooks/twilio",
            data=_form("message-2", "customer-1", "second"),
        )
        assert provider.wait_for_received(2)
        assert not generator.second_started.wait(timeout=0.05)
        generator.release_first.set()
        first_response = first.result(timeout=2.0)
        second_response = second.result(timeout=2.0)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert generator.calls == ["first", "second"]
    history = SqliteConversationStore(database_path).get_history(
        provider="test-provider",
        customer_address="customer-1",
    )
    assert [(item.direction, item.body) for item in history] == [
        ("inbound", "first"),
        ("inbound", "second"),
        ("outbound", "reply:first"),
        ("outbound", "reply:second"),
    ]


def test_active_predecessor_returns_503_then_provider_retry_processes_message(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "retry-webhook.db"
    store = SqliteConversationStore(database_path)
    store.initialize()
    first_message = InboundMessage(
        provider="test-provider",
        provider_message_id="message-1",
        customer_address="customer-1",
        recipient_address="studio",
        body="first",
    )
    first = store.claim_generation(first_message)
    assert first.owner_token is not None
    clock = FakeClock()
    generator = RecordingGenerator()
    app = create_app(
        _settings(database_path),
        provider=FormProvider(),
        store=store,
        generator=generator,
        monotonic_clock=clock,
        sleeper=clock.sleep,
    )

    with TestClient(app) as client:
        blocked_response = client.post(
            "/webhooks/twilio",
            data=_form("message-2", "customer-1", "second"),
        )
        blocked_history = store.get_history(
            provider="test-provider",
            customer_address="customer-1",
        )
        assert store.complete_generation(
            inbound_message_id=first.inbound_message_id,
            owner_token=first.owner_token,
            reply_body="reply:first",
        )
        retry_response = client.post(
            "/webhooks/twilio",
            data=_form("message-2", "customer-1", "second changed on retry"),
        )

    assert blocked_response.status_code == 503
    assert "reply:" not in blocked_response.text
    assert [(item.direction, item.body) for item in blocked_history] == [
        ("inbound", "first"),
        ("inbound", "second"),
    ]
    assert retry_response.status_code == 200
    assert retry_response.text == "reply:second"
    assert generator.calls == ["second"]


def test_distinct_conversations_generate_in_parallel(tmp_path: Path) -> None:
    provider = FormProvider()
    generator = ParallelGenerator()
    app = create_app(
        _settings(tmp_path / "parallel.db"),
        provider=provider,
        generator=generator,
    )

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            client.post,
            "/webhooks/twilio",
            data=_form("message-1", "customer-1", "first"),
        )
        second = executor.submit(
            client.post,
            "/webhooks/twilio",
            data=_form("message-2", "customer-2", "second"),
        )
        responses = [first.result(timeout=2.0), second.result(timeout=2.0)]

    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(generator.calls) == ["first", "second"]


def test_concurrent_retries_run_generator_once_and_replay_reply(tmp_path: Path) -> None:
    provider = FormProvider()
    generator = OrderedBlockingGenerator()
    app = create_app(
        _settings(tmp_path / "same-message.db"),
        provider=provider,
        generator=generator,
    )
    form = _form("same-message", "customer-1", "first")

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.post, "/webhooks/twilio", data=form)
        assert generator.first_started.wait(timeout=1.0)
        retry = executor.submit(client.post, "/webhooks/twilio", data=form)
        assert provider.wait_for_received(2)
        generator.release_first.set()
        responses = [first.result(timeout=2.0), retry.result(timeout=2.0)]

    assert [response.status_code for response in responses] == [200, 200]
    assert [response.text for response in responses] == ["reply:first", "reply:first"]
    assert generator.calls == ["first"]


def test_time_spent_before_admission_prevents_late_generation_but_persists_inbound(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "late.db"
    clock = FakeClock()
    generator = RecordingGenerator()
    app = create_app(
        _settings(database_path),
        provider=FormProvider(receive_delay=clock),
        generator=generator,
        monotonic_clock=clock,
        sleeper=clock.sleep,
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            data=_form("message-1", "customer-1", "late"),
        )

    assert response.status_code == 503
    assert generator.calls == []
    lifecycle = SqliteConversationStore(database_path).get_generation(
        provider="test-provider",
        provider_message_id="message-1",
    )
    assert lifecycle is not None
    assert lifecycle.state is GenerationState.RETRYABLE
    assert lifecycle.attempt_count == 0


def test_render_deadline_failure_retries_with_persisted_reply_without_regeneration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "render.db"
    clock = FakeClock()
    provider = FirstRenderConsumesDeadlineProvider(clock)
    generator = RecordingGenerator()
    app = create_app(
        _settings(database_path),
        provider=provider,
        generator=generator,
        monotonic_clock=clock,
        sleeper=clock.sleep,
    )
    form = _form("message-1", "customer-1", "render")

    with TestClient(app) as client:
        first = client.post("/webhooks/twilio", data=form)
        retry = client.post("/webhooks/twilio", data=form)

    assert first.status_code == 503
    assert retry.status_code == 200
    assert retry.text == "reply:render"
    assert generator.calls == ["render"]
    assert provider.reply_attempts == 2


def test_webhook_persists_privacy_safe_generation_metric(tmp_path: Path) -> None:
    database_path = tmp_path / "metrics-webhook.db"
    app = create_app(
        _settings(database_path),
        provider=FormProvider(),
        generator=MetricGenerator(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            data=_form("message-1", "customer-phone", "sensitive body"),
        )

    assert response.status_code == 200
    store = SqliteConversationStore(database_path)
    lifecycle = store.get_generation(provider="test-provider", provider_message_id="message-1")
    assert lifecycle is not None
    assert store.get_generation_metrics(inbound_message_id=lifecycle.inbound_message_id) == [
        GenerationMetricRecord(
            attempt_number=1,
            provider="anthropic",
            model="claude-sonnet-5",
            configuration="thinking=disabled;format=json_schema;max_tokens=200",
            latency_ms=120,
            input_tokens=100,
            output_tokens=25,
            total_tokens=125,
            estimated_cost_microusd=675,
            outcome="success",
            error_code=None,
        )
    ]


def test_llm_failure_persists_safe_metrics_without_an_invalid_reply(tmp_path: Path) -> None:
    database_path = tmp_path / "failed-metrics-webhook.db"
    generator = FailingMetricGenerator()
    app = create_app(
        _settings(database_path),
        provider=FormProvider(),
        generator=generator,
    )

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/twilio",
            data=_form("message-1", "customer-phone", "sensitive body"),
        )

    assert response.status_code == 200
    assert response.text == "safe reply"
    assert generator.calls == 2
    store = SqliteConversationStore(database_path)
    lifecycle = store.get_generation(provider="test-provider", provider_message_id="message-1")
    assert lifecycle is not None
    metrics = store.get_generation_metrics(inbound_message_id=lifecycle.inbound_message_id)
    assert [(metric.attempt_number, metric.outcome, metric.error_code) for metric in metrics] == [
        (1, "failure", "provider_timeout"),
        (2, "failure", "provider_timeout"),
    ]
