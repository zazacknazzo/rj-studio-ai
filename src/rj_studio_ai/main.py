from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    ProviderWebhookRequest,
    WhatsAppProvider,
)
from rj_studio_ai.providers.twilio import TwilioProvider


def create_app(
    settings: Settings | None = None,
    *,
    provider: WhatsAppProvider | None = None,
    store: SqliteConversationStore | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_provider = provider or TwilioProvider(
        auth_token=resolved_settings.twilio_auth_token,
        validate_signature=resolved_settings.twilio_validate_signature,
        public_webhook_url=resolved_settings.twilio_public_webhook_url,
    )
    resolved_store = store or SqliteConversationStore(resolved_settings.database_path)
    responder = MessageResponder(
        store=resolved_store,
        automatic_reply=resolved_settings.automatic_reply,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_store.initialize()
        yield

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)

    def configuration_is_valid() -> bool:
        return resolved_provider.is_configured() and bool(resolved_settings.automatic_reply.strip())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def readiness() -> JSONResponse:
        checks = {
            "configuration": ("ok" if configuration_is_valid() else "failed"),
            "database": "ok" if resolved_store.is_writable() else "failed",
            "migrations": ("ok" if resolved_store.migrations_are_current() else "failed"),
        }
        is_ready = all(result == "ok" for result in checks.values())
        return JSONResponse(
            status_code=(status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE),
            content={"status": "ready" if is_ready else "not_ready", "checks": checks},
        )

    @app.post("/webhooks/twilio")
    @app.post("/webhooks/whatsapp")
    async def whatsapp_webhook(request: Request) -> Response:
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
            message = resolved_provider.receive(webhook)
            reply = await run_in_threadpool(responder.handle, message)
            provider_response = resolved_provider.reply(reply)
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

        return Response(
            content=provider_response.body,
            media_type=provider_response.media_type,
            status_code=provider_response.status_code,
        )

    return app


app = create_app()
