"""Runtime Responses adapter; returns an untrusted proposal, never a customer delivery."""

import asyncio
from collections.abc import Callable
from time import monotonic

import httpx

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.domain import InboundMessage
from rj_studio_ai.generation import (
    GeneratedReply,
    GenerationFailure,
    GenerationMetric,
    GenerationTimeout,
    TransientGenerationError,
)
from rj_studio_ai.llm_decision import (
    MAX_OUTPUT_TOKENS,
    StructuredDecisionValidationError,
    validate_llm_decision,
)
from rj_studio_ai.providers.openai_contract import (
    Usage,
    UsageValidationError,
    incomplete_reason,
    response_decision_proposal,
    response_request,
    response_status,
)


class OpenAIReplyGenerator:
    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-6.1-sol",
        reasoning_effort: str = "low",
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        if (
            model != "gpt-6.1-sol"
            or reasoning_effort not in {"low", "medium"}
            or type(max_output_tokens) is not int
            or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise ValueError("provider_configuration")
        self._api_key = api_key
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self._client_factory = client_factory or (lambda: httpx.AsyncClient())
        self._configuration = (
            f"effort={reasoning_effort};tier=default;max_output_tokens={max_output_tokens}"
        )

    def is_configured(self) -> bool:
        return bool(self._api_key.strip())

    def generate(
        self,
        message: InboundMessage,
        *,
        context: ConversationContext | None = None,
        remaining_budget: float,
    ) -> GeneratedReply:
        if not self.is_configured():
            raise GenerationFailure("provider_configuration")
        if remaining_budget < 1:
            raise GenerationTimeout("provider_timeout")
        context = context or ConversationContext(history=(), knowledge=())
        payload = response_request(
            message,
            context,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            max_output_tokens=self.max_output_tokens,
        )
        started = monotonic()
        data = None
        usage = None
        error_code = None
        error_type = GenerationFailure
        try:
            response = asyncio.run(self._request(payload, remaining_budget))
            if response.status_code != 200:
                error_type, error_code = self._http_error(response.status_code)
            else:
                data = response.json()
                usage = Usage.from_response(data)
                if data.get("model") != self.model or data.get("service_tier") != "default":
                    error_code = "invalid_provider_response"
                elif response_status(data) != "completed":
                    error_code = "provider_incomplete"
                else:
                    decision = validate_llm_decision(
                        response_decision_proposal(data),
                        allowed_knowledge_refs={
                            fact.id for fact in context.knowledge if fact.status == "approved"
                        },
                    )
        except (TimeoutError, httpx.TimeoutException):
            error_type, error_code = GenerationTimeout, "provider_timeout"
        except httpx.HTTPError:
            error_type, error_code = TransientGenerationError, "provider_connection"
        except UsageValidationError as error:
            error_code = error.code
        except (StructuredDecisionValidationError, ValueError, KeyError, TypeError):
            error_code = "invalid_structured_decision"
        metric = GenerationMetric(
            provider=self.provider,
            model=self.model,
            configuration=self._configuration,
            latency_ms=max(0, round((monotonic() - started) * 1000)),
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            total_tokens=usage.input_tokens + usage.output_tokens if usage else None,
            estimated_cost_microusd=None,
            outcome="failure" if error_code else "success",
            error_code=error_code,
            cached_input_tokens=usage.cached_tokens if usage else None,
            cache_write_tokens=usage.cache_write_tokens if usage else None,
            reasoning_tokens=usage.reasoning_tokens if usage else None,
            response_status=response_status(data) if data is not None else None,
            incomplete_reason=incomplete_reason(data),
        )
        if error_code:
            raise error_type(error_code, metric) from None
        return GeneratedReply(decision=decision, metric=metric)

    @staticmethod
    def _http_error(status: int) -> tuple[type[GenerationFailure], str]:
        if status in {401, 403}:
            return GenerationFailure, "provider_authentication"
        if status == 429:
            return TransientGenerationError, "provider_rate_limit"
        if status >= 500:
            return TransientGenerationError, "provider_unavailable"
        return GenerationFailure, "provider_request"

    async def _request(self, payload: dict, remaining_budget: float) -> httpx.Response:
        # HTTPX read timeout alone is per-read, not a total execution deadline.
        # Cancellation encloses request AND client cleanup; transport has no retries.
        async with asyncio.timeout(remaining_budget):
            async with self._client_factory() as client:
                return await client.post(
                    "https://api.openai.com/v1/responses",
                    json=payload,
                    headers={"Authorization": "Bearer " + self._api_key},
                    timeout=httpx.Timeout(
                        remaining_budget,
                        connect=min(5.0, remaining_budget),
                        write=min(5.0, remaining_budget),
                        pool=min(5.0, remaining_budget),
                    ),
                )
