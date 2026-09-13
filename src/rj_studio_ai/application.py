from rj_studio_ai.domain import WebhookInput, WebhookResponse
from rj_studio_ai.persistence import SqliteConversationStore
from rj_studio_ai.providers.base import WhatsAppProvider


class MessageResponder:
    def __init__(
        self,
        *,
        provider: WhatsAppProvider,
        store: SqliteConversationStore,
        automatic_reply: str,
    ) -> None:
        self._provider = provider
        self._store = store
        self._automatic_reply = automatic_reply

    def handle(self, webhook: WebhookInput) -> WebhookResponse:
        message = self._provider.receive(webhook)
        is_first_delivery = self._store.record_exchange(message, self._automatic_reply)
        if not is_first_delivery:
            return self._provider.acknowledge()
        return self._provider.reply(message, self._automatic_reply)
