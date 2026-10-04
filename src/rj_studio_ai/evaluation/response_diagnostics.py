"""Allowlisted response accounting metadata; never retains provider output."""

from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from rj_studio_ai.evaluation.live_billing import UsageValidationCode
from rj_studio_ai.evaluation.records import Count, RecordModel, check_privacy

ResponseStatus = Literal[
    "completed", "incomplete", "failed", "in_progress", "queued", "cancelled", "unrecognized"
]
TransportError = Literal[
    "read_timeout", "connect_timeout", "write_timeout", "pool_timeout", "transport_error"
]


def installed_sdk_version():
    try:
        return version("openai")
    except PackageNotFoundError:
        return "not-installed"


class ResponseDiagnostics(RecordModel):
    response_status: ResponseStatus | None = None
    incomplete_reason_present: StrictBool | None = None
    incomplete_reason: Literal["max_output_tokens", "content_filter", "unrecognized"] | None = None
    usage_present: StrictBool | None = None
    input_tokens_present: StrictBool | None = None
    output_tokens_present: StrictBool | None = None
    total_tokens_present: StrictBool | None = None
    cached_tokens_present: StrictBool | None = None
    cache_write_tokens_present: StrictBool | None = None
    reasoning_tokens_present: StrictBool | None = None
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    total_tokens: Count | None = None
    cached_tokens: Count | None = None
    cache_write_tokens: Count | None = None
    reasoning_tokens: Count | None = None
    usage_validation_error_code: UsageValidationCode | None = None
    sdk_version: str = Field(
        default_factory=installed_sdk_version,
        pattern=r"^(not-installed|\d+\.\d+\.\d+[a-zA-Z0-9.+-]*)$",
    )
    http_success: StrictBool | None = None
    http_status_code: int | None = Field(default=None, ge=100, le=599)
    transport_error_code: TransportError | None = None

    @model_validator(mode="after")
    def private_metadata(self):
        check_privacy(self.model_dump(mode="json"))
        return self

    def observe(self, data):
        if not isinstance(data, dict):
            return self
        status = data.get("status")
        usage = data.get("usage")
        details = data.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        observed = {
            "response_status": status
            if isinstance(status, str)
            and status
            in {"completed", "incomplete", "failed", "in_progress", "queued", "cancelled"}
            else "unrecognized",
            "usage_present": usage is not None,
            "incomplete_reason_present": reason is not None,
            "incomplete_reason": reason
            if isinstance(reason, str) and reason in {"max_output_tokens", "content_filter"}
            else "unrecognized"
            if reason is not None
            else None,
        }
        usage = usage if isinstance(usage, dict) else {}
        input_details = usage.get("input_tokens_details")
        output_details = usage.get("output_tokens_details")
        input_details = input_details if isinstance(input_details, dict) else {}
        output_details = output_details if isinstance(output_details, dict) else {}
        for source, name in (
            (usage, "input_tokens"),
            (usage, "output_tokens"),
            (usage, "total_tokens"),
            (input_details, "cached_tokens"),
            (input_details, "cache_write_tokens"),
            (output_details, "reasoning_tokens"),
        ):
            value = source.get(name)
            observed[name + "_present"] = value is not None
            observed[name] = value if type(value) is int and value >= 0 else None
        return type(self).model_validate({**self.model_dump(), **observed})
