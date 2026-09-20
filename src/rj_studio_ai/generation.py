from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.llm_decision import Intent, LLMDecision, UncertaintyLevel

if TYPE_CHECKING:
    from rj_studio_ai.conversation_context import ConversationContext


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
    decision: LLMDecision
    metric: GenerationMetric | None = None

    @property
    def reply_body(self) -> str:
        return self.decision.reply_text

    @classmethod
    def from_reply_text(
        cls,
        reply_text: str,
        *,
        metric: GenerationMetric | None = None,
    ) -> "GeneratedReply":
        """Construct the deterministic V0/V1 test fallback as a typed proposal."""
        return cls(
            decision=LLMDecision(
                intents=(Intent.OTHER,),
                reply_text=reply_text,
                uncertainty=UncertaintyLevel.HIGH,
                knowledge_refs=(),
                critical_claims=(),
                handoff=False,
                handoff_reason=None,
            ),
            metric=metric,
        )


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
    def generate(
        self,
        message: InboundMessage,
        *,
        context: "ConversationContext | None" = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        """Generate one candidate reply within the supplied remaining budget."""

    def is_configured(self) -> bool:
        """Return whether this generator has its required local configuration."""


class FixedReplyGenerator:
    """Deterministic ticket-02 generator; real LLM providers arrive in ticket 03."""

    def __init__(self, reply_body: str) -> None:
        self._reply_body = reply_body

    def generate(
        self,
        message: InboundMessage,
        *,
        context: "ConversationContext | None" = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        del message, context, remaining_budget
        return GeneratedReply.from_reply_text(self._reply_body)

    def is_configured(self) -> bool:
        return bool(self._reply_body.strip())
