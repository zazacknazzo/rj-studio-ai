from typing import Protocol

from rj_studio_ai.domain import InboundMessage


class TransientGenerationError(RuntimeError):
    """A generation attempt failed safely and may be retried."""


class GenerationTimeout(TransientGenerationError):
    """A generation attempt exhausted its supplied time budget."""


class ReplyGenerator(Protocol):
    def generate(self, message: InboundMessage, *, remaining_budget: float) -> str:
        """Generate one candidate reply within the supplied remaining budget."""


class FixedReplyGenerator:
    """Deterministic ticket-02 generator; real LLM providers arrive in ticket 03."""

    def __init__(self, reply_body: str) -> None:
        self._reply_body = reply_body

    def generate(self, message: InboundMessage, *, remaining_budget: float) -> str:
        del message, remaining_budget
        return self._reply_body
