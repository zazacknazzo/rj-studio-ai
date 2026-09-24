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
from rj_studio_ai.delivery import OutboundDeliveryExecutor
from rj_studio_ai.domain import DeliveryStatusReceived, InboundMessageReceived
from rj_studio_ai.generation import ReplyGenerator
from rj_studio_ai.persistence import (
    DeliveryState,
    PersistenceUnavailable,
    SqliteConversationStore,
)
from rj_studio_ai.processing import ProcessingExecutor, ProcessingRunner
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundMessageSender,
    ProviderWebhookRequest,
    WhatsAppProvider,
)
from rj_studio_ai.providers.twilio import TwilioOutboundSender, TwilioProvider
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
    processing_executor: ProcessingExecutor | None = None,
    monotonic_clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_provider = provider or TwilioProvider(
        auth_token=resolved_settings.twilio_auth_token,
        validate_signature=resolved_settings.twilio_validate_signature,
        public_webhook_url=resolved_settings.twilio_public_webhook_url,
        public_status_callback_url=resolved_settings.twilio_status_callback_url,
    )
    resolved_store = store or SqliteConversationStore(
        resolved_settings.database_path,
        busy_timeout_seconds=resolved_settings.sqlite_busy_timeout_seconds,
    )
    resolved_generator = generator or generator_from_settings(resolved_settings)
    resolved_salon_knowledge = salon_knowledge or SalonKnowledgeRepository(
        resolved_settings.salon_knowledge_path
    )
    resolved_outbound_sender = outbound_sender
    outbound_executor: OutboundDeliveryExecutor | None = None
    if resolved_settings.delivery_mode == "proactive":
        resolved_outbound_sender = resolved_outbound_sender or TwilioOutboundSender(
            account_sid=resolved_settings.twilio_account_sid,
            api_key_sid=resolved_settings.twilio_api_key_sid,
            api_key_secret=resolved_settings.twilio_api_key_secret,
            status_callback_url=resolved_settings.twilio_status_callback_url or "",
        )
        outbound_executor = OutboundDeliveryExecutor(
            store=resolved_store,
            sender=resolved_outbound_sender,
            request_timeout_seconds=resolved_settings.outbound_request_timeout_seconds,
            poll_interval_seconds=resolved_settings.outbound_poll_interval_seconds,
            concurrency=resolved_settings.outbound_concurrency,
            maximum_attempts=resolved_settings.outbound_maximum_attempts,
            retry_backoff_base_seconds=(resolved_settings.outbound_retry_backoff_base_seconds),
            retry_backoff_maximum_seconds=(
                resolved_settings.outbound_retry_backoff_maximum_seconds
            ),
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
        completion_delivery_state=(
            DeliveryState.PENDING
            if resolved_settings.delivery_mode == "proactive"
            else DeliveryState.UNKNOWN
        ),
    )
    resolved_processing_executor = processing_executor
    if resolved_settings.delivery_mode == "proactive" and resolved_processing_executor is None:
        resolved_processing_executor = ProcessingExecutor(
            runner=ProcessingRunner(
                store=resolved_store,
                responder=responder,
                monotonic_clock=monotonic_clock,
            ),
            poll_interval_seconds=resolved_settings.processing_poll_interval_seconds,
            concurrency=resolved_settings.processing_concurrency,
            on_completion=outbound_executor.wake if outbound_executor is not None else None,
        )

    def outbound_configuration_is_valid() -> bool:
        if resolved_settings.delivery_mode == "legacy":
            return True
        if resolved_outbound_sender is None:
            return False
        if isinstance(resolved_outbound_sender, TwilioOutboundSender):
            return resolved_outbound_sender.is_configured()
        return True

    legacy_mode_safe_at_start = False

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal legacy_mode_safe_at_start
        resolved_store.initialize()
        resolved_salon_knowledge.load()
        if resolved_settings.delivery_mode == "legacy":
            try:
                legacy_mode_safe_at_start = resolved_store.legacy_delivery_mode_is_safe()
            except PersistenceUnavailable:
                legacy_mode_safe_at_start = False
        executor_configuration_ready = (
            configuration_is_valid()
            and resolved_settings.app_process_count == 1
            and resolved_store.migrations_are_current()
            and resolved_store.is_writable()
            and all(value == "ok" for value in resolved_store.sqlite_durability_checks().values())
        )
        if outbound_executor is not None and executor_configuration_ready:
            outbound_executor.start()
        if resolved_processing_executor is not None and executor_configuration_ready:
            resolved_processing_executor.start()
        try:
            yield
        finally:
            if resolved_processing_executor is not None:
                resolved_processing_executor.stop()
            if outbound_executor is not None:
                outbound_executor.stop()

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.outbound_sender = resolved_outbound_sender
    app.state.outbound_executor = outbound_executor
    app.state.processing_executor = resolved_processing_executor

    def configuration_is_valid() -> bool:
        return (
            resolved_provider.is_configured()
            and bool(resolved_settings.automatic_reply.strip())
            and resolved_generator.is_configured()
            and resolved_salon_knowledge.is_loaded()
            and outbound_configuration_is_valid()
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def readiness() -> JSONResponse:
        delivery_mode_safe = (
            resolved_settings.delivery_mode == "proactive" or legacy_mode_safe_at_start
        )
        checks = {
            "configuration": ("ok" if configuration_is_valid() else "failed"),
            "sqlite_single_process": (
                "ok" if resolved_settings.app_process_count == 1 else "failed"
            ),
            "database": "ok" if resolved_store.is_writable() else "failed",
            "migrations": ("ok" if resolved_store.migrations_are_current() else "failed"),
            **resolved_store.sqlite_durability_checks(),
        }
        checks["delivery_mode"] = "ok" if delivery_mode_safe else "failed"
        if resolved_settings.delivery_mode == "proactive":
            checks["outbound_executor"] = (
                "ok" if outbound_executor is not None and outbound_executor.is_alive() else "failed"
            )
            checks["processing_executor"] = (
                "ok"
                if resolved_processing_executor is not None
                and resolved_processing_executor.is_alive()
                else "failed"
            )
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
            if resolved_settings.delivery_mode == "proactive":
                local_readiness = await run_in_threadpool(readiness)
                if local_readiness.status_code != status.HTTP_200_OK:
                    raise RetryableWebhookError("Proactive ingress is not locally ready")
                if not batch.events or any(
                    not isinstance(event, InboundMessageReceived) for event in batch.events
                ):
                    raise InvalidWebhookPayload("Unsupported provider webhook event")
                for event in batch.events:
                    await run_in_threadpool(
                        resolved_store.admit_generation,
                        event,
                        lock_timeout=deadline.remaining_budget(),
                    )
                if deadline.is_expired():
                    raise RetryableWebhookError(
                        "Webhook deadline expired before provider acknowledgement"
                    )
                provider_response = resolved_provider.acknowledge()
                if resolved_processing_executor is None:
                    raise RetryableWebhookError("Processing Executor is unavailable")
                resolved_processing_executor.wake()
                legacy_customer_reply = False
            else:
                if len(batch.events) != 1 or not isinstance(
                    batch.events[0], InboundMessageReceived
                ):
                    raise InvalidWebhookPayload("Unsupported provider webhook event")
                event = batch.events[0]
                reply = await run_in_threadpool(responder.handle, event, deadline=deadline)
                if deadline.is_expired():
                    raise RetryableWebhookError(
                        "Webhook deadline expired before provider rendering"
                    )
                delivery = resolved_store.get_delivery_for_provider_inbound(
                    provider=event.provider,
                    provider_message_id=event.provider_message_id,
                    lock_timeout=deadline.remaining_budget(),
                )
                if delivery is None:
                    raise RetryableWebhookError("Outbound Delivery is unavailable")
                legacy_customer_reply = delivery.state is DeliveryState.ACCEPTED_LEGACY or (
                    delivery.state is DeliveryState.UNKNOWN
                    and delivery.safe_error_code == "legacy_unverified"
                )
                provider_response = (
                    resolved_provider.render_legacy_reply(reply)
                    if legacy_customer_reply
                    else resolved_provider.acknowledge()
                )
            response = Response(
                content=provider_response.body,
                media_type=provider_response.media_type,
                status_code=provider_response.status_code,
            )
            if deadline.is_expired():
                raise RetryableWebhookError("Webhook deadline expired during provider rendering")
            if legacy_customer_reply and (
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

    @app.post("/webhooks/twilio/status")
    async def twilio_status_callback(request: Request) -> Response:
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
            if any(not isinstance(event, DeliveryStatusReceived) for event in batch.events):
                raise InvalidWebhookPayload("Unsupported provider status event")
            for event in batch.events:
                resolved_store.record_delivery_status(event)
            acknowledgement = resolved_provider.acknowledge()
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
                detail="Delivery status persistence is unavailable",
            ) from error
        return Response(
            content=acknowledgement.body,
            media_type=acknowledgement.media_type,
            status_code=acknowledgement.status_code,
        )

    return app


app = create_app()
