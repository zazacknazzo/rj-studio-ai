"""Eval-only Responses adapter. Never constructed by the production provider factory."""

import json
from time import monotonic

import httpx
from pydantic import StrictBool, model_validator

from rj_studio_ai.appointment_intake import APPOINTMENT_EXTRACTION_INSTRUCTIONS
from rj_studio_ai.evaluation.live_billing import BudgetLedger, Usage
from rj_studio_ai.evaluation.records import Attempt, check_privacy, fingerprint
from rj_studio_ai.generation import GeneratedReply, GenerationFailure, GenerationMetric
from rj_studio_ai.livia_persona import LiviaPersona, reply_plan_instructions
from rj_studio_ai.llm_decision import (
    MAX_OUTPUT_TOKENS,
    decision_json_schema,
    validate_llm_decision,
)


class LiveAttempt(Attempt):
    usage: Usage | None
    pricing_verified: StrictBool = True

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
    def __init__(self, *, api_key: str, client: httpx.Client, ledger: BudgetLedger, phase: str):
        self._api_key = api_key
        self.client = client
        self.ledger = ledger
        self.phase = phase
        self.attempts = []
        self.decisions = []
        self.stop_code = None
        self.request_hashes = []

    def is_configured(self):
        return bool(self._api_key)

    def generate(self, message, *, context, remaining_budget):
        if self.stop_code is not None:
            raise GenerationFailure(self.stop_code)
        started = monotonic()
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
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        check_privacy(payload)
        headers = {"Authorization": "Bearer " + self._api_key}
        # Counting does not generate an answer. Include exactly the same input/schema.
        count_payload = {
            k: payload[k] for k in ("model", "instructions", "input", "reasoning", "text")
        }
        try:
            count_response = self.client.post(
                "https://api.openai.com/v1/responses/input_tokens",
                headers=headers,
                json=count_payload,
                timeout=max(0.001, remaining_budget),
            )
            if count_response.status_code != 200:
                raise ValueError("input_count_failed")
            input_count = count_response.json()["input_tokens"]
            if type(input_count) is not int or not 1 <= input_count <= 16_000:
                raise ValueError("input_count_invalid")
            remaining = remaining_budget - (monotonic() - started)
            if remaining < 1:
                raise ValueError("preflight_deadline")
            self.ledger.reserve(
                self.phase, input_bound=input_count + 1024, output_bound=MAX_OUTPUT_TOKENS
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

        model_started = monotonic()
        usage = None
        decision = None
        error_code = None
        data = None
        pricing_verified = False
        try:
            response = self.client.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload,
                timeout=remaining,
            )
            if response.status_code != 200:
                raise ValueError("live_http_failure")
            data = response.json()
            usage = Usage.from_response(data)
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
            check_privacy(raw_decision)
            decision = validate_llm_decision(
                raw_decision, allowed_knowledge_refs={f.id for f in context.knowledge}
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # No raw exception, headers, response body or reasoning is exported.
            error_code = "live_transport_or_response_failure"
            if isinstance(data, dict):
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
        latency = (monotonic() - model_started) * 1000
        try:
            cost = self.ledger.settle(usage if pricing_verified else None)
        except ValueError:
            cost = None
            error_code = "live_accounting_failure"
        if usage is None:
            error_code = "live_usage_missing_or_invalid"
        attempt = LiveAttempt(
            number=len(self.attempts) + 1,
            outcome="failure" if error_code else "success",
            billable=True if usage is not None else None,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            usage=usage,
            pricing_verified=pricing_verified,
            latency_ms=latency,
            error_code=error_code,
        )
        self.attempts.append(attempt)
        self.request_hashes.append(fingerprint(payload))
        self.decisions.append(decision)
        metric = GenerationMetric(
            provider="openai",
            model="gpt-6.1-sol",
            configuration="effort=medium;tier=default;max_output_tokens=200",
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
