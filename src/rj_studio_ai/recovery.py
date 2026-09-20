from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.persistence import (
    GenerationRecoveryBlocked,
    GenerationRecoveryNotAvailable,
    GenerationState,
    PendingGeneration,
    SqliteConversationStore,
)

RecoveryBlocked = GenerationRecoveryBlocked
RecoveryNotAvailable = GenerationRecoveryNotAvailable


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    inbound_message_id: int
    state: GenerationState
    reply_persisted: bool


class PendingGenerationRecovery:
    """Runs one explicitly selected pending Message through the normal responder."""

    def __init__(
        self,
        *,
        store: SqliteConversationStore,
        responder: MessageResponder,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._store = store
        self._responder = responder
        self._monotonic_clock = monotonic_clock

    def list_pending(self) -> list[PendingGeneration]:
        return self._store.list_pending_generations()

    def recover(self, inbound_message_id: int) -> RecoveryResult:
        message = self._store.load_recoverable_inbound_message(
            inbound_message_id=inbound_message_id
        )
        self._responder.handle(
            message,
            deadline=ExecutionDeadline.start(clock=self._monotonic_clock),
        )
        lifecycle = self._store.get_generation(
            provider=message.provider,
            provider_message_id=message.provider_message_id,
        )
        if lifecycle is None or lifecycle.state is not GenerationState.COMPLETED:
            raise RecoveryNotAvailable("Recovery did not produce a terminal AI Reply")
        return RecoveryResult(
            inbound_message_id=lifecycle.inbound_message_id,
            state=lifecycle.state,
            reply_persisted=lifecycle.reply_body is not None,
        )
