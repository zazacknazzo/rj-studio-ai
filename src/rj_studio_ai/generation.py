from dataclasses import dataclass, replace
from typing import Protocol

from rj_studio_ai.domain import InboundMessage


@dataclass(frozen=True, slots=True)
class GenerationMetric:
    provider: str
    model: str
    configuration: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_microusd: int | None
    outcome: str
    error_code: str | None


@dataclass(frozen=True, slots=True)
class GeneratedReply:
    reply_body: str
    metric: GenerationMetric | None = None


class GenerationFailure(RuntimeError):
    def __init__(self, error_code: str, metric: GenerationMetric | None = None) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.metric = (
            None if metric is None else replace(metric, outcome="failure", error_code=error_code)
        )


class TransientGenerationError(GenerationFailure):
    """A generation attempt failed safely and may be retried."""


class GenerationTimeout(TransientGenerationError):
    """A generation attempt exhausted its supplied time budget."""


class ReplyGenerator(Protocol):
    def generate(self, message: InboundMessage, *, remaining_budget: float) -> GeneratedReply:
        """Generate one candidate reply within the supplied remaining budget."""

    def is_configured(self) -> bool:
        """Return whether this generator has its required local configuration."""


class FixedReplyGenerator:
    """Deterministic ticket-02 generator; real LLM providers arrive in ticket 03."""

    def __init__(self, reply_body: str) -> None:
        self._reply_body = reply_body

    def generate(self, message: InboundMessage, *, remaining_budget: float) -> GeneratedReply:
        del message, remaining_budget
        return GeneratedReply(reply_body=self._reply_body)

    def is_configured(self) -> bool:
        return bool(self._reply_body.strip())
