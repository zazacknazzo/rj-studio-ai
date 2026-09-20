import asyncio
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Protocol

import anthropic

from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import (
    GeneratedReply,
    GenerationFailure,
    GenerationMetric,
    GenerationTimeout,
    TransientGenerationError,
)
from rj_studio_ai.livia_persona import LiviaPersona
from rj_studio_ai.llm_decision import (
    MAX_OUTPUT_TOKENS,
    LLMDecision,
    StructuredDecisionValidationError,
    decision_json_schema,
    validate_llm_decision,
)
from rj_studio_ai.salon_knowledge import SalonKnowledgeStatus

if TYPE_CHECKING:
    from rj_studio_ai.conversation_context import ConversationContext


class AnthropicMessages(Protocol):
    def create(self, **kwargs: object) -> object: ...


class AnthropicClient(Protocol):
    messages: AnthropicMessages


@dataclass(frozen=True, slots=True)
class LLMPriceTable:
    """Configured, reviewable rates in microdollars per one million tokens."""

    input_microusd_per_million: int
    output_microusd_per_million: int

    def is_valid(self) -> bool:
        return self.input_microusd_per_million >= 0 and self.output_microusd_per_million >= 0

    def estimate_microusd(self, input_tokens: int | None, output_tokens: int | None) -> int | None:
        if input_tokens is None or output_tokens is None:
            return None
        return (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
        ) // 1_000_000


class AnthropicReplyGenerator:
    provider = "anthropic"
    _minimum_request_budget_seconds = 1.0
    _system_prompt = (
        "Responda em português brasileiro, de forma breve. "
        "Não invente fatos do salão; peça esclarecimento quando faltar contexto. "
        "Produza somente a decisão estruturada, sem raciocínio textual."
    )
    _decision_schema = decision_json_schema()
    _persona = LiviaPersona()

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int,
        pricing: LLMPriceTable | None,
        client: AnthropicClient | None = None,
        client_factory: Callable[[], AnthropicClient] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if client is not None and client_factory is not None:
            raise ValueError("Provide either an Anthropic client or a client factory")
        if not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
            raise ValueError(
                f"Anthropic output token limit must be between 1 and {MAX_OUTPUT_TOKENS}"
            )
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._pricing = pricing
        if client_factory is not None:
            self._client_factory = client_factory
        elif client is not None:
            self._client_factory = lambda: client
        else:
            self._client_factory = self._new_client
        self._clock = clock
        self._configuration = (
            f"thinking=disabled;format=json_schema;max_tokens={self._max_output_tokens}"
        )

    def is_configured(self) -> bool:
        return bool(
            self._api_key.strip()
            and self._model.strip()
            and self._max_output_tokens > 0
            and self._pricing is not None
            and self._pricing.is_valid()
        )

    def generate(
        self,
        message: InboundMessage,
        *,
        context: "ConversationContext | None" = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        if not self.is_configured():
            raise GenerationFailure("provider_configuration")
        if remaining_budget < self._minimum_request_budget_seconds:
            raise GenerationTimeout("provider_timeout")

        started_at = self._clock()
        try:
            response = asyncio.run(self._request(message, context, remaining_budget))
        except TimeoutError as error:
            raise GenerationTimeout("provider_timeout", self._failure_metric(started_at)) from error
        except anthropic.APITimeoutError as error:
            raise GenerationTimeout("provider_timeout", self._failure_metric(started_at)) from error
        except anthropic.APIConnectionError as error:
            raise TransientGenerationError(
                "provider_connection", self._failure_metric(started_at)
            ) from error
        except anthropic.RateLimitError as error:
            raise TransientGenerationError(
                "provider_rate_limit", self._failure_metric(started_at)
            ) from error
        except (
            anthropic.ServiceUnavailableError,
            anthropic.OverloadedError,
            anthropic.InternalServerError,
            anthropic.DeadlineExceededError,
        ) as error:
            raise TransientGenerationError(
                "provider_unavailable", self._failure_metric(started_at)
            ) from error
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as error:
            raise GenerationFailure(
                "provider_authentication", self._failure_metric(started_at)
            ) from error
        except anthropic.APIStatusError as error:
            if error.status_code >= 500:
                raise TransientGenerationError(
                    "provider_unavailable", self._failure_metric(started_at)
                ) from error
            raise GenerationFailure("provider_request", self._failure_metric(started_at)) from error
        except anthropic.APIResponseValidationError as error:
            raise TransientGenerationError(
                "invalid_provider_response", self._failure_metric(started_at)
            ) from error

        try:
            decision = self._decision(response, context)
            self._persona.validate_reply(
                message.body,
                decision.reply_text,
                prior_ai_replies=(
                    ()
                    if context is None
                    else tuple(turn.body for turn in context.history if turn.role == "ai_attendant")
                ),
            )
        except (
            StructuredDecisionValidationError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise TransientGenerationError(
                "invalid_structured_decision", self._failure_metric(started_at, response)
            ) from error

        input_tokens, output_tokens = self._usage_tokens(response)
        return GeneratedReply(
            decision=decision,
            metric=GenerationMetric(
                provider=self.provider,
                model=str(getattr(response, "model", self._model)),
                configuration=self._configuration,
                latency_ms=self._latency_ms(started_at),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    None
                    if input_tokens is None or output_tokens is None
                    else input_tokens + output_tokens
                ),
                estimated_cost_microusd=self._pricing.estimate_microusd(
                    input_tokens, output_tokens
                ),
                outcome="success",
                error_code=None,
            ),
        )

    def _new_client(self) -> AnthropicClient:
        return anthropic.AsyncAnthropic(api_key=self._api_key, max_retries=0)

    async def _request(
        self,
        message: InboundMessage,
        context: "ConversationContext | None",
        remaining_budget: float,
    ) -> object:
        client = self._client_factory()
        loop = asyncio.get_running_loop()
        request_deadline = loop.time() + remaining_budget
        async with asyncio.timeout(remaining_budget):
            try:
                response = client.messages.create(
                    model=self._model,
                    max_tokens=self._max_output_tokens,
                    thinking={"type": "disabled"},
                    output_config={
                        "format": {"type": "json_schema", "schema": self._decision_schema}
                    },
                    system=self._system_prompt_for(context),
                    messages=self._messages_for(message, context),
                    timeout=remaining_budget,
                )
                return await response if inspect.isawaitable(response) else response
            finally:
                if loop.time() < request_deadline:
                    await self._close_quietly(client)

    @staticmethod
    async def _close_quietly(client: AnthropicClient) -> None:
        close = getattr(client, "close", None)
        if close is None:
            return
        try:
            closing = close()
            if inspect.isawaitable(closing):
                await closing
        except Exception:
            return

    def _failure_metric(
        self, started_at: float, response: object | None = None
    ) -> GenerationMetric:
        input_tokens, output_tokens = self._usage_tokens(response)
        return GenerationMetric(
            provider=self.provider,
            model=self._model,
            configuration=self._configuration,
            latency_ms=self._latency_ms(started_at) if started_at else 0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                None
                if input_tokens is None or output_tokens is None
                else input_tokens + output_tokens
            ),
            estimated_cost_microusd=self._pricing.estimate_microusd(input_tokens, output_tokens),
            outcome="failure",
            error_code=None,
        )

    def _latency_ms(self, started_at: float) -> int:
        return max(0, round((self._clock() - started_at) * 1_000))

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None

    def _usage_tokens(self, response: object | None) -> tuple[int | None, int | None]:
        usage = getattr(response, "usage", None)
        return (
            self._optional_int(getattr(usage, "input_tokens", None)),
            self._optional_int(getattr(usage, "output_tokens", None)),
        )

    @staticmethod
    def _decision(
        response: object,
        context: "ConversationContext | None",
    ) -> LLMDecision:
        content = getattr(response, "content", None)
        if not isinstance(content, list) or len(content) != 1:
            raise ValueError("Expected one structured text content block")
        block = content[0]
        if getattr(block, "type", None) != "text" or not isinstance(
            getattr(block, "text", None), str
        ):
            raise ValueError("Expected structured text content block")
        payload = json.loads(block.text)
        allowed_knowledge_refs = (
            set()
            if context is None
            else {
                fact.id
                for fact in context.knowledge
                if fact.status is SalonKnowledgeStatus.APPROVED
            }
        )
        return validate_llm_decision(payload, allowed_knowledge_refs=allowed_knowledge_refs)

    @classmethod
    def _system_prompt_for(cls, context: "ConversationContext | None") -> str:
        prompt = f"{cls._system_prompt}\n\n{cls._persona.instructions}"
        if context is not None and context.history_may_be_incomplete:
            prompt += (
                " O histórico anterior pode estar incompleto; não deduza o que falta "
                "e peça esclarecimento quando isso for relevante."
            )
        approved_knowledge = (
            ()
            if context is None
            else tuple(
                fact for fact in context.knowledge if fact.status is SalonKnowledgeStatus.APPROVED
            )
        )
        if approved_knowledge:
            knowledge = "\n\n".join(fact.context_text() for fact in approved_knowledge)
            prompt += f"\n\nApproved Salon Knowledge:\n{knowledge}"
        return prompt

    @staticmethod
    def _messages_for(
        message: InboundMessage,
        context: "ConversationContext | None",
    ) -> list[dict[str, str]]:
        history = () if context is None else context.history
        messages = [
            {
                "role": "user" if turn.role == "customer" else "assistant",
                "content": turn.body,
            }
            for turn in history
        ]
        messages.append({"role": "user", "content": message.body})
        return messages
