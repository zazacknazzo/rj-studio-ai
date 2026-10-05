"""Responses wire contract shared by runtime and live eval; no orchestration or billing."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rj_studio_ai.appointment_intake import (
    APPOINTMENT_EXTRACTION_INSTRUCTIONS,
    appointment_constraints,
)
from rj_studio_ai.livia_persona import LiviaPersona, reply_plan_instructions
from rj_studio_ai.llm_decision import decision_json_schema

Count = Annotated[int, Field(strict=True, ge=0)]

UsageValidationCode = Literal[
    "usage_absent",
    "usage_invalid_shape",
    "usage_input_tokens_missing",
    "usage_output_tokens_missing",
    "usage_total_tokens_missing",
    "usage_cache_breakdown_missing",
    "usage_cached_tokens_missing",
    "usage_cache_write_tokens_missing",
    "usage_count_invalid",
    "usage_input_breakdown",
    "usage_output_breakdown",
    "usage_total_mismatch",
]


class UsageValidationError(ValueError):
    """A controlled accounting code, never a provider value or raw exception."""

    def __init__(self, code: UsageValidationCode):
        self.code = code
        super().__init__(code)


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_tokens: Count
    cached_tokens: Count
    cache_write_tokens: Count
    output_tokens: Count
    reasoning_tokens: Count | None

    @model_validator(mode="after")
    def consistent(self):
        if self.cached_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError("usage_input_breakdown")
        if self.reasoning_tokens is not None and self.reasoning_tokens > self.output_tokens:
            raise ValueError("usage_output_breakdown")
        return self

    @classmethod
    def from_response(cls, response):
        if not isinstance(response, dict):
            raise UsageValidationError("usage_invalid_shape")
        usage = response.get("usage")
        if usage is None:
            raise UsageValidationError("usage_absent")
        if not isinstance(usage, dict):
            raise UsageValidationError("usage_invalid_shape")

        def count(source, key, missing_code):
            value = source.get(key)
            if value is None:
                raise UsageValidationError(missing_code)
            if type(value) is not int or value < 0:
                raise UsageValidationError("usage_count_invalid")
            return value

        input_tokens = count(usage, "input_tokens", "usage_input_tokens_missing")
        output_tokens = count(usage, "output_tokens", "usage_output_tokens_missing")
        total_tokens = count(usage, "total_tokens", "usage_total_tokens_missing")
        details = usage.get("input_tokens_details")
        if details is None:
            raise UsageValidationError("usage_cache_breakdown_missing")
        if not isinstance(details, dict):
            raise UsageValidationError("usage_invalid_shape")
        cached_tokens = count(details, "cached_tokens", "usage_cached_tokens_missing")
        cache_write_tokens = count(
            details, "cache_write_tokens", "usage_cache_write_tokens_missing"
        )
        output_details = usage.get("output_tokens_details")
        if output_details is not None and not isinstance(output_details, dict):
            raise UsageValidationError("usage_invalid_shape")
        reasoning_tokens = (
            count(output_details, "reasoning_tokens", "usage_count_invalid")
            if output_details and output_details.get("reasoning_tokens") is not None
            else None
        )
        if cached_tokens + cache_write_tokens > input_tokens:
            raise UsageValidationError("usage_input_breakdown")
        if reasoning_tokens is not None and reasoning_tokens > output_tokens:
            raise UsageValidationError("usage_output_breakdown")
        if total_tokens != input_tokens + output_tokens:
            raise UsageValidationError("usage_total_mismatch")
        return cls(
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )


def decision_instructions(context):
    """Same institutional instructions and context as the existing runtime adapter."""
    prompt = (
        "Responda em português brasileiro, de forma breve. "
        "Não invente fatos do salão; peça esclarecimento quando faltar contexto. "
        "Produza somente a decisão estruturada, sem raciocínio textual."
        f"\n\n{LiviaPersona().instructions}\n\n{reply_plan_instructions()}"
        f"\n\n{APPOINTMENT_EXTRACTION_INSTRUCTIONS}"
    )
    prompt += "\n\n" + appointment_constraints(context.appointment_intake)
    if context.history_may_be_incomplete:
        prompt += (
            " O histórico anterior pode estar incompleto; não deduza o que falta "
            "e peça esclarecimento quando isso for relevante."
        )
    if context.knowledge:
        knowledge = "\n\n".join(fact.context_text() for fact in context.knowledge)
        prompt += f"\n\nApproved Salon Knowledge:\n{knowledge}"
    return prompt


def response_request(message, context, *, model, reasoning_effort, max_output_tokens):
    content = message.body
    if context.appointment_intake is not None and context.appointment_intake.state == "collecting":
        content = context.appointment_intake.context_text() + "\n\n" + content
    return {
        "model": model,
        "instructions": decision_instructions(context),
        "input": [
            {"role": "user" if turn.role == "customer" else "assistant", "content": turn.body}
            for turn in context.history
        ]
        + [{"role": "user", "content": content}],
        "reasoning": {"effort": reasoning_effort},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "rj_decision",
                "strict": True,
                "schema": decision_json_schema(),
            }
        },
        "store": False,
        "service_tier": "default",
        "max_output_tokens": max_output_tokens,
    }


def response_status(data):
    status = data.get("status") if isinstance(data, dict) else None
    return (
        status
        if isinstance(status, str)
        and status in {"completed", "incomplete", "failed", "in_progress", "queued", "cancelled"}
        else "unrecognized"
    )


def incomplete_reason(data):
    details = data.get("incomplete_details") if isinstance(data, dict) else None
    reason = details.get("reason") if isinstance(details, dict) else None
    return (
        reason
        if isinstance(reason, str) and reason in {"max_output_tokens", "content_filter"}
        else "unrecognized"
        if reason is not None
        else None
    )


def response_decision_proposal(data):
    if response_status(data) != "completed":
        raise ValueError("incomplete_output")
    texts = [
        part["text"]
        for item in data["output"]
        if item["type"] == "message"
        for part in item["content"]
        if part["type"] == "output_text"
    ]
    if len(texts) != 1:
        raise ValueError("missing_decision")
    return json.loads(texts[0])
