from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.domain import AIReply, InboundMessageReceived, ProviderWebhookEventBatch
from rj_studio_ai.generation import FixedReplyGenerator, GeneratedReply
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import (
    DeliveryState,
    GenerationState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.processing import ProcessingRunner
from rj_studio_ai.providers.base import (
    ProviderAcceptance,
    ProviderWebhookRequest,
    ProviderWebhookResponse,
    WhatsAppProvider,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

FORM = {
    "MessageSid": "SM-async-inbound",
    "From": "whatsapp:+5511999999999",
    "To": "whatsapp:+14155238886",
    "Body": "Mensagem sintética",
}


class _RecordingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self, message: object, *, context: object, remaining_budget: float
    ) -> GeneratedReply:
        self.calls += 1
        return GeneratedReply.from_reply_text("Resposta sintética")

    def is_configured(self) -> bool:
        return True


class _BlockingGenerator:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def generate(
        self, message: object, *, context: object, remaining_budget: float
    ) -> GeneratedReply:
        self.entered.set()
        assert self.release.wait(timeout=3.0)
        return GeneratedReply.from_reply_text("Resposta posterior")

    def is_configured(self) -> bool:
        return True


class _PausedExecutor:
    def __init__(self) -> None:
        self.alive = False
        self.wakes = 0

    def start(self) -> None:
        self.alive = True

    def stop(self) -> None:
        self.alive = False

    def wake(self) -> None:
        self.wakes += 1

    def is_alive(self) -> bool:
        return self.alive


class _UnavailableIngressStore(SqliteConversationStore):
    def admit_generation(self, *args: object, **kwargs: object) -> object:
        raise PersistenceUnavailable("synthetic commit failure")


class _BatchProvider(WhatsAppProvider):
    def __init__(self, store: SqliteConversationStore) -> None:
        self.store = store
        self.acknowledgements = 0

    def receive(self, webhook: ProviderWebhookRequest) -> ProviderWebhookEventBatch:
        del webhook
        return ProviderWebhookEventBatch(
            events=(
                InboundMessageReceived(
                    provider="batch-provider",
                    provider_message_id="inbound-1",
                    customer_address="customer-a",
                    recipient_address="studio",
                    body="Primeira",
                ),
                InboundMessageReceived(
                    provider="batch-provider",
                    provider_message_id="inbound-2",
                    customer_address="customer-a",
                    recipient_address="studio",
                    body="Segunda",
                ),
            )
        )

    def acknowledge(self) -> ProviderWebhookResponse:
        for identifier in ("inbound-1", "inbound-2"):
            lifecycle = self.store.get_generation(
                provider="batch-provider", provider_message_id=identifier
            )
            assert lifecycle is not None
            assert lifecycle.state is GenerationState.RETRYABLE
        self.acknowledgements += 1
        return ProviderWebhookResponse(body="", media_type="text/plain")

    def render_legacy_reply(self, reply: AIReply) -> ProviderWebhookResponse:
        raise AssertionError(f"Unexpected legacy reply: {reply.body}")

    def is_configured(self) -> bool:
        return True


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        twilio_validate_signature=False,
        delivery_mode="proactive",
    )


def test_proactive_webhook_commits_once_then_acknowledges_without_llm_or_outbound(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ingress.db"
    generator = _RecordingGenerator()
    sender = DeterministicFakeOutboundSender(outcomes=[])
    executor = _PausedExecutor()
    app = create_app(
        _settings(database_path),
        generator=generator,
        outbound_sender=sender,
        processing_executor=executor,
    )

    with TestClient(app) as client:
        first = client.post("/webhooks/twilio", data=FORM)
        duplicate = client.post("/webhooks/twilio", data=FORM)
        persisted = SqliteConversationStore(database_path).get_generation(
            provider="twilio", provider_message_id=FORM["MessageSid"]
        )
        ready = client.get("/ready")
        executor.stop()
        stopped = client.get("/ready")

    assert first.status_code == duplicate.status_code == 200
    assert "<Message>" not in first.text
    assert "<Message>" not in duplicate.text
    assert persisted is not None
    assert persisted.state is GenerationState.RETRYABLE
    assert persisted.reply_body is None
    assert generator.calls == 0
    assert sender.calls == []
    assert executor.wakes == 2
    assert ready.status_code == 200
    assert stopped.status_code == 503
    assert stopped.json()["checks"]["processing_executor"] == "failed"

    store = SqliteConversationStore(database_path)
    processed = ProcessingRunner(
        store=store,
        responder=MessageResponder(
            store=store,
            generator=FixedReplyGenerator("Resposta posterior"),
            safe_failure_reply="Resposta segura",
            completion_delivery_state=DeliveryState.PENDING,
        ),
    ).run_once()
    assert processed is not None
    assert store.get_delivery_for_inbound(processed.inbound_message_id) is not None
    assert len(store.get_history(provider="twilio", customer_address=FORM["From"])) == 2


def test_proactive_ingress_failure_cannot_return_success_ack(tmp_path: Path) -> None:
    database_path = tmp_path / "failed-commit.db"
    store = _UnavailableIngressStore(database_path)
    app = create_app(
        _settings(database_path),
        store=store,
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
        processing_executor=_PausedExecutor(),
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=FORM)

    assert response.status_code == 503
    assert store.get_history(provider="twilio", customer_address=FORM["From"]) == []


def test_batch_ack_follows_each_durable_inbound_and_duplicates_are_independent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "batch.db"
    store = SqliteConversationStore(database_path)
    provider = _BatchProvider(store)
    generator = _RecordingGenerator()
    app = create_app(
        _settings(database_path),
        store=store,
        provider=provider,
        generator=generator,
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
        processing_executor=_PausedExecutor(),
    )

    with TestClient(app) as client:
        first = client.post("/webhooks/twilio", content=b"synthetic")
        duplicate = client.post("/webhooks/twilio", content=b"synthetic")

    assert first.status_code == duplicate.status_code == 200
    assert provider.acknowledgements == 2
    assert generator.calls == 0
    assert len(store.get_history(provider="batch-provider", customer_address="customer-a")) == 2


def test_proactive_ingress_rejects_unsafe_multi_process_configuration(tmp_path: Path) -> None:
    database_path = tmp_path / "unsafe-process-count.db"
    settings = Settings(
        _env_file=None,
        database_path=database_path,
        twilio_validate_signature=False,
        delivery_mode="proactive",
        app_process_count=2,
    )
    app = create_app(
        settings,
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[]),
        processing_executor=_PausedExecutor(),
    )

    with TestClient(app) as client:
        response = client.post("/webhooks/twilio", data=FORM)

    assert response.status_code == 503
    assert (
        SqliteConversationStore(database_path).get_history(
            provider="twilio", customer_address=FORM["From"]
        )
        == []
    )


def test_proactive_http_ack_does_not_wait_for_active_llm(tmp_path: Path) -> None:
    database_path = tmp_path / "nonblocking-ack.db"
    generator = _BlockingGenerator()
    app = create_app(
        _settings(database_path),
        generator=generator,
        outbound_sender=DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("PM-async")]),
    )

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        try:
            response = pool.submit(client.post, "/webhooks/twilio", data=FORM).result(timeout=2.0)
            assert response.status_code == 200
            assert "<Message>" not in response.text
            assert generator.entered.wait(timeout=2.0)
        finally:
            generator.release.set()
