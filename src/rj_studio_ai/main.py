from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from time import monotonic, sleep

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from rj_studio_ai.application import MessageResponder, RetryableWebhookError
from rj_studio_ai.config import Settings
from rj_studio_ai.conversation_context import ConversationContextBuilder, ConversationContextLimits
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.domain import InboundMessageReceived
from rj_studio_ai.generation import ReplyGenerator
from rj_studio_ai.persistence import (
    DeliveryState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundMessageSender,
    ProviderWebhookRequest,
    WhatsAppProvider,
)
from rj_studio_ai.providers.twilio import TwilioProvider
from rj_studio_ai.runtime import generator_from_settings
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository


def create_app(
    settings: Settings | None = None,
    *,
    provider: WhatsAppProvider | None = None,
    store: SqliteConversationStore | None = None,
    generator: ReplyGenerator | None = None,
    salon_knowledge: SalonKnowledgeRepository | None = None,
    outbound_sender: OutboundMessageSender | None = None,
    monotonic_clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_provider = provider or TwilioProvider(
        auth_token=resolved_settings.twilio_auth_token,
        validate_signature=resolved_settings.twilio_validate_signature,
        public_webhook_url=resolved_settings.twilio_public_webhook_url,
    )
    resolved_store = store or SqliteConversationStore(
        resolved_settings.database_path,
        busy_timeout_seconds=resolved_settings.sqlite_busy_timeout_seconds,
    )
    resolved_generator = generator or generator_from_settings(resolved_settings)
    resolved_salon_knowledge = salon_knowledge or SalonKnowledgeRepository(
        resolved_settings.salon_knowledge_path
    )
    responder = MessageResponder(
        store=resolved_store,
        generator=resolved_generator,
        safe_failure_reply=resolved_settings.automatic_reply,
        context_builder=ConversationContextBuilder(
            store=resolved_store,
            salon_knowledge=resolved_salon_knowledge,
            limits=ConversationContextLimits(
                maximum_prior_messages=resolved_settings.conversation_context_maximum_messages,
                maximum_age=timedelta(days=resolved_settings.conversation_context_maximum_age_days),
                history_token_budget=resolved_settings.conversation_context_history_token_budget,
                total_input_token_budget=resolved_settings.llm_input_token_budget,
            ),
        ),
        sleeper=sleeper,
        completion_delivery_state=DeliveryState.UNKNOWN,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_store.initialize()
        resolved_salon_knowledge.load()
        yield

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.outbound_sender = outbound_sender

    def configuration_is_valid() -> bool:
        return (
            resolved_provider.is_configured()
            and bool(resolved_settings.automatic_reply.strip())
            and resolved_generator.is_configured()
            and resolved_salon_knowledge.is_loaded()
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def readiness() -> JSONResponse:
        checks = {
            "configuration": ("ok" if configuration_is_valid() else "failed"),
            "sqlite_single_process": (
                "ok" if resolved_settings.app_process_count == 1 else "failed"
            ),
            "database": "ok" if resolved_store.is_writable() else "failed",
            "migrations": ("ok" if resolved_store.migrations_are_current() else "failed"),
            **resolved_store.sqlite_durability_checks(),
        }
        is_ready = all(result == "ok" for result in checks.values())
        return JSONResponse(
            status_code=(status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE),
            content={"status": "ready" if is_ready else "not_ready", "checks": checks},
        )

    @app.post("/webhooks/twilio")
    @app.post("/webhooks/whatsapp")
    async def whatsapp_webhook(request: Request) -> Response:
        deadline = ExecutionDeadline.start(clock=monotonic_clock)
        if not configuration_is_valid():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WhatsApp provider is not configured",
            )
        webhook = ProviderWebhookRequest(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
            query_string=request.scope.get("query_string", b""),
            content_type=request.headers.get("content-type", ""),
            body=await request.body(),
        )

        try:
            batch = resolved_provider.receive(webhook)
            if len(batch.events) != 1 or not isinstance(batch.events[0], InboundMessageReceived):
                raise InvalidWebhookPayload("Unsupported provider webhook event")
            event = batch.events[0]
            reply = await run_in_threadpool(responder.handle, event, deadline=deadline)
            if deadline.is_expired():
                raise RetryableWebhookError("Webhook deadline expired before provider rendering")
            provider_response = resolved_provider.render_legacy_reply(reply)
            response = Response(
                content=provider_response.body,
                media_type=provider_response.media_type,
                status_code=provider_response.status_code,
            )
            if deadline.is_expired():
                raise RetryableWebhookError("Webhook deadline expired during provider rendering")
            if (
                200 <= provider_response.status_code < 300
                and not resolved_store.confirm_legacy_delivery(
                    provider=event.provider,
                    inbound_provider_message_id=event.provider_message_id,
                    lock_timeout=deadline.remaining_budget(),
                )
            ):
                raise RetryableWebhookError("Legacy delivery could not be confirmed")
        except InvalidWebhookSignature as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except InvalidWebhookPayload as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except PersistenceUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Conversation persistence is unavailable",
            ) from error
        except RetryableWebhookError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook processing should be retried",
            ) from error

        return response

    return app


app = create_app()
