"""Eval-only Responses adapter. Never constructed by the production provider factory."""

import json
from time import monotonic

import httpx
from pydantic import StrictBool, model_validator

from rj_studio_ai.appointment_intake import APPOINTMENT_EXTRACTION_INSTRUCTIONS
from rj_studio_ai.evaluation.decision_trace import DecisionTraceCapture
from rj_studio_ai.evaluation.latency import LatencyRecorder
from rj_studio_ai.evaluation.live_billing import (
    LIVE_MAX_OUTPUT_TOKENS,
    BudgetLedger,
    Usage,
    UsageValidationError,
)
from rj_studio_ai.evaluation.records import Attempt, check_privacy, fingerprint
from rj_studio_ai.evaluation.response_diagnostics import ResponseDiagnostics
from rj_studio_ai.generation import GeneratedReply, GenerationFailure, GenerationMetric
from rj_studio_ai.livia_persona import LiviaPersona, reply_plan_instructions
from rj_studio_ai.llm_decision import (
    StructuredDecisionValidationError,
    decision_json_schema,
    validate_llm_decision,
)

LIVE_CONNECT_TIMEOUT_SECONDS = 5.0
LIVE_INPUT_COUNT_TIMEOUT_SECONDS = 5.0


class LiveAttempt(Attempt):
    usage: Usage | None
    pricing_verified: StrictBool = True
    response_diagnostics: ResponseDiagnostics | None = None

    @model_validator(mode="after")
    def matching_usage(self):
        if self.usage is not None and (
            self.input_tokens != self.usage.input_tokens
            or self.output_tokens != self.usage.output_tokens
            or self.billable is not True
        ):
            raise ValueError("attempt_usage_mismatch")
        if self.usage is None and (self.input_tokens is not None or self.output_tokens is not None):
            raise ValueError("attempt_usage_missing")
        return self


def eval_prompt(context):
    """Same institutional instructions and context as the existing runtime adapter."""
    prompt = (
        "Responda em português brasileiro, de forma breve. "
        "Não invente fatos do salão; peça esclarecimento quando faltar contexto. "
        "Produza somente a decisão estruturada, sem raciocínio textual."
        f"\n\n{LiviaPersona().instructions}\n\n{reply_plan_instructions()}"
        f"\n\n{APPOINTMENT_EXTRACTION_INSTRUCTIONS}"
    )
    if context.history_may_be_incomplete:
        prompt += (
            " O histórico anterior pode estar incompleto; não deduza o que falta "
            "e peça esclarecimento quando isso for relevante."
        )
    if context.knowledge:
        knowledge = "\n\n".join(fact.context_text() for fact in context.knowledge)
        prompt += f"\n\nApproved Salon Knowledge:\n{knowledge}"
    return prompt


class OpenAIEvalGenerator:
    def __init__(
        self, *, api_key: str, client: httpx.Client, ledger: BudgetLedger, phase: str, timing=None
    ):
        self._api_key = api_key
        self.client = client
        self.ledger = ledger
        self.phase = phase
        self.attempts = []
        self.decisions = []
        self.stop_code = None
        self.request_hashes = []
        self.trace_capture = DecisionTraceCapture()
        self.timing = timing or LatencyRecorder(clock=monotonic)

    def is_configured(self):
        return bool(self._api_key)

    def generate(self, message, *, context, remaining_budget):
        if self.stop_code is not None:
            raise GenerationFailure(self.stop_code)
        started = monotonic()
        with self.timing.measure("eval_bookkeeping_ms"):
            self.trace_capture.propose(None, context)
        schema = decision_json_schema()
        content = message.body
        if (
            context.appointment_intake is not None
            and context.appointment_intake.state == "collecting"
        ):
            content = context.appointment_intake.context_text() + "\n\n" + content
        payload = {
            "model": self.ledger.pricing.model,
            "instructions": eval_prompt(context),
            "input": [
                {"role": "user" if turn.role == "customer" else "assistant", "content": turn.body}
                for turn in context.history
            ]
            + [{"role": "user", "content": content}],
            "reasoning": {"effort": "medium"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "rj_decision",
                    "strict": True,
                    "schema": schema,
                }
            },
            "store": False,
            "service_tier": "default",
            "max_output_tokens": LIVE_MAX_OUTPUT_TOKENS,
        }
        check_privacy(payload)
        headers = {"Authorization": "Bearer " + self._api_key}
        # Counting does not generate an answer. Include exactly the same input/schema.
        count_payload = {
            k: payload[k] for k in ("model", "instructions", "input", "reasoning", "text")
        }
        try:
            with self.timing.measure("input_count_ms"):
                count_response = self.client.post(
                    "https://api.openai.com/v1/responses/input_tokens",
                    headers=headers,
                    json=count_payload,
                    timeout=httpx.Timeout(
                        max(0.001, min(LIVE_INPUT_COUNT_TIMEOUT_SECONDS, remaining_budget)),
                        connect=max(0.001, min(LIVE_CONNECT_TIMEOUT_SECONDS, remaining_budget)),
                    ),
                )
                if count_response.status_code != 200:
                    raise ValueError("input_count_failed")
                input_count = count_response.json()["input_tokens"]
                if type(input_count) is not int or not 1 <= input_count <= 16_000:
                    raise ValueError("input_count_invalid")
            remaining = remaining_budget - (monotonic() - started)
            if remaining < 1:
                raise ValueError("preflight_deadline")
            with self.timing.measure("budget_reservation_ms"):
                self.ledger.reserve(
                    self.phase, input_bound=input_count + 1024, output_bound=LIVE_MAX_OUTPUT_TOKENS
                )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            self.stop_code = (
                str(error)
                if str(error)
                in {
                    "budget_exhausted",
                    "unresolved_submission",
                    "input_count_failed",
                    "input_count_invalid",
                    "preflight_deadline",
                }
                else "live_preflight_failure"
            )
            raise GenerationFailure(self.stop_code) from None

        usage = None
        decision = None
        error_code = None
        data = None
        pricing_verified = False
        diagnostics = ResponseDiagnostics()
        response = None
        try:
            with self.timing.measure("model_request_ms") as request_time:
                response = self.client.post(
                    "https://api.openai.com/v1/responses",
                    headers=headers,
                    json=payload,
                    timeout=httpx.Timeout(
                        remaining,
                        connect=min(LIVE_CONNECT_TIMEOUT_SECONDS, remaining),
                        write=min(LIVE_CONNECT_TIMEOUT_SECONDS, remaining),
                        pool=min(LIVE_CONNECT_TIMEOUT_SECONDS, remaining),
                    ),
                )
            with self.timing.measure("decision_validation_ms"):
                diagnostics = diagnostics.model_copy(
                    update={
                        "http_success": response.is_success,
                        "http_status_code": response.status_code,
                    }
                )
                if response.status_code != 200:
                    raise ValueError("live_http_failure")
                data = response.json()
                diagnostics = diagnostics.observe(data)
                try:
                    usage = Usage.from_response(data)
                except UsageValidationError as error:
                    diagnostics = diagnostics.model_copy(
                        update={"usage_validation_error_code": error.code}
                    )
                    if isinstance(data, dict) and data.get("status") != "completed":
                        raise ValueError("live_incomplete_output") from None
                    raise
                if data.get("model") != self.ledger.pricing.model:
                    raise ValueError("live_model_mismatch")
                if data.get("service_tier") != "default":
                    raise ValueError("live_tier_mismatch")
                pricing_verified = True
                if data.get("status") != "completed":
                    raise ValueError("live_incomplete_output")
                texts = [
                    part["text"]
                    for item in data["output"]
                    if item["type"] == "message"
                    for part in item["content"]
                    if part["type"] == "output_text"
                ]
                if len(texts) != 1:
                    raise ValueError("live_missing_decision")
                raw_decision = json.loads(texts[0])
                with self.timing.measure("eval_bookkeeping_ms"):
                    self.trace_capture.propose(raw_decision, context)
                check_privacy(raw_decision)
                try:
                    decision = validate_llm_decision(
                        raw_decision, allowed_knowledge_refs={f.id for f in context.knowledge}
                    )
                except StructuredDecisionValidationError as error:
                    self.trace_capture.rejected(
                        "invalid_reference"
                        if str(error)
                        in {
                            "Structured decision references unavailable knowledge",
                            "Critical factual claim must declare its knowledge reference",
                            "Fact reply part must declare its knowledge reference",
                        }
                        else "invalid_decision"
                    )
                    raise
                if monotonic() - started >= remaining_budget:
                    raise ValueError("live_observation_timeout")
        except UsageValidationError as error:
            error_code = "live_" + error.code
        except httpx.HTTPError as error:
            code = next(
                (
                    code
                    for kind, code in (
                        (httpx.ReadTimeout, "read_timeout"),
                        (httpx.ConnectTimeout, "connect_timeout"),
                        (httpx.WriteTimeout, "write_timeout"),
                        (httpx.PoolTimeout, "pool_timeout"),
                    )
                    if isinstance(error, kind)
                ),
                "transport_error",
            )
            diagnostics = diagnostics.model_copy(update={"transport_error_code": code})
            error_code = "live_" + code
        except (ValueError, KeyError, TypeError) as error:
            # No raw exception, headers, response body or reasoning is exported.
            error_code = "live_transport_or_response_failure"
            if str(error) == "live_observation_timeout":
                error_code = "live_observation_timeout"
                decision = None
            elif isinstance(data, dict):
                if data.get("model") != self.ledger.pricing.model:
                    error_code = "live_model_mismatch"
                elif data.get("service_tier") != "default":
                    error_code = "live_tier_mismatch"
                elif data.get("status") != "completed":
                    error_code = "live_incomplete_output"
                elif usage is None:
                    error_code = "live_usage_missing_or_invalid"
                else:
                    error_code = "live_decision_invalid"
            elif response is not None:
                error_code = (
                    "live_http_failure"
                    if response.status_code != 200
                    else "live_response_json_invalid"
                )
        latency = request_time.elapsed_ms
        try:
            with self.timing.measure("eval_bookkeeping_ms"):
                cost = self.ledger.settle(usage if pricing_verified else None)
        except ValueError:
            cost = None
            error_code = "live_accounting_failure"
        attempt = LiveAttempt(
            number=len(self.attempts) + 1,
            outcome="failure" if error_code else "success",
            billable=True if usage is not None else None,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            usage=usage,
            pricing_verified=pricing_verified,
            response_diagnostics=diagnostics,
            latency_ms=latency,
            error_code=error_code,
        )
        with self.timing.measure("eval_bookkeeping_ms"):
            self.attempts.append(attempt)
            self.request_hashes.append(fingerprint(payload))
            self.decisions.append(decision)
        metric = GenerationMetric(
            provider="openai",
            model="gpt-6.1-sol",
            configuration=f"effort=medium;tier=default;max_output_tokens={LIVE_MAX_OUTPUT_TOKENS}",
            latency_ms=round(latency),
            input_tokens=attempt.input_tokens,
            output_tokens=attempt.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens if usage else None,
            estimated_cost_microusd=int(cost * 1_000_000) if cost is not None else None,
            outcome=attempt.outcome,
            error_code=error_code,
        )
        if error_code:
            self.stop_code = error_code
            raise GenerationFailure(error_code, metric)
        return GeneratedReply(decision=decision, metric=metric)
