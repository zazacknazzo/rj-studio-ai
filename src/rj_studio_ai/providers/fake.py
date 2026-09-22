from collections import deque
from collections.abc import Iterable
from typing import TypeAlias

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.providers.base import (
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
    ProviderAcceptance,
)

ProgrammedOutboundOutcome: TypeAlias = (
    ProviderAcceptance | OutboundRetryableError | OutboundPermanentError | OutboundOutcomeUnknown
)


class DeterministicFakeOutboundSender(OutboundMessageSender):
    """Record calls and consume one explicit result or failure per send."""

    def __init__(self, *, outcomes: Iterable[ProgrammedOutboundOutcome]) -> None:
        programmed = tuple(outcomes)
        supported = (
            ProviderAcceptance,
            OutboundRetryableError,
            OutboundPermanentError,
            OutboundOutcomeUnknown,
        )
        if any(not isinstance(outcome, supported) for outcome in programmed):
            raise TypeError("Unsupported outbound outcome")
        self._outcomes = deque(programmed)
        self.calls: list[tuple[OutboundMessage, float]] = []

    def send(
        self,
        message: OutboundMessage,
        *,
        timeout_seconds: float,
    ) -> ProviderAcceptance:
        self.calls.append((message, timeout_seconds))
        if not self._outcomes:
            raise AssertionError("No programmed outbound outcome")
        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
