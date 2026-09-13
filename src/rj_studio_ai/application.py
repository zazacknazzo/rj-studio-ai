from rj_studio_ai.domain import AutomaticReply, InboundMessage
from rj_studio_ai.persistence import SqliteConversationStore


class MessageResponder:
    def __init__(
        self,
        *,
        store: SqliteConversationStore,
        automatic_reply: str,
    ) -> None:
        self._store = store
        self._automatic_reply = automatic_reply

    def handle(self, message: InboundMessage) -> AutomaticReply:
        reply_body = self._store.get_or_create_reply(message, self._automatic_reply)
        return AutomaticReply(body=reply_body)
