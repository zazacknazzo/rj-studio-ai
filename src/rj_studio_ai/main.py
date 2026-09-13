from fastapi import FastAPI, HTTPException, Request, Response, status

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.domain import WebhookInput
from rj_studio_ai.persistence import SqliteConversationStore
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
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
    )
    resolved_store = store or SqliteConversationStore(resolved_settings.database_path)
    responder = MessageResponder(
        provider=resolved_provider,
        store=resolved_store,
        automatic_reply=resolved_settings.automatic_reply,
    )

    app = FastAPI(title=resolved_settings.app_name)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/whatsapp")
    async def whatsapp_webhook(request: Request) -> Response:
        form = {key: str(value) for key, value in (await request.form()).items()}
        public_url = resolved_settings.twilio_public_webhook_url or str(request.url)
        webhook = WebhookInput(
            url=public_url,
            headers=dict(request.headers),
            form=form,
        )

        try:
            provider_response = responder.handle(webhook)
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

        return Response(
            content=provider_response.body,
            media_type=provider_response.media_type,
            status_code=provider_response.status_code,
        )

    return app


app = create_app()
