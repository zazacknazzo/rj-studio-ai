"""Standard OpenAI accounting and a single-process, crash-conservative spend journal."""

import fcntl
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from rj_studio_ai.evaluation.records import Count, RecordModel
from rj_studio_ai.llm_decision import MAX_OUTPUT_TOKENS

PRICING_PATH = Path("docs/evals/V1/pricing.openai-2026-10-02.json")
# Shared Phase 1.2 ceiling; explicit lower runtime configuration is still honored.
LIVE_MAX_OUTPUT_TOKENS = MAX_OUTPUT_TOKENS


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


class Usage(RecordModel):
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


class LivePricing(RecordModel):
    version: Literal["openai-standard-2026-10-02-v1"]
    provider: Literal["openai"]
    model: Literal["gpt-6.1-sol"]
    service_tier: Literal["default"]
    reviewed_at: date
    approved_by: Literal["product-owner"]
    source: Literal["https://developers.openai.com/api/docs/models/gpt-6.1-sol"]
    usage_source: Literal["https://developers.openai.com/api/docs/guides/prompt-caching"]
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    cache_write_usd_per_million: Decimal
    output_usd_per_million: Decimal

    @model_validator(mode="after")
    def verified_rates(self):
        if self.reviewed_at != date(2026, 10, 2) or (
            self.input_usd_per_million,
            self.cached_input_usd_per_million,
            self.cache_write_usd_per_million,
            self.output_usd_per_million,
        ) != (Decimal("2"), Decimal("0.10"), Decimal("2.50"), Decimal("10")):
            raise ValueError("pricing_inconsistent")
        return self

    @classmethod
    def load(cls, path=PRICING_PATH):
        return cls.model_validate_json(Path(path).read_text())

    def cost(self, usage: Usage) -> Decimal:
        ordinary = usage.input_tokens - usage.cached_tokens - usage.cache_write_tokens
        return (
            ordinary * self.input_usd_per_million
            + usage.cached_tokens * self.cached_input_usd_per_million
            + usage.cache_write_tokens * self.cache_write_usd_per_million
            + usage.output_tokens * self.output_usd_per_million
        ) / 1_000_000


class BudgetLedger:
    """Fsync a worst-case reservation before submission. Ambiguity stops all further work."""

    def __init__(
        self, path: Path, pricing: LivePricing, *, phase_a_cap=Decimal("1"), global_cap=Decimal("5")
    ):
        if not Decimal("0") < phase_a_cap <= Decimal("1"):
            raise ValueError("invalid_phase_cap")
        if not phase_a_cap <= global_cap <= Decimal("5"):
            raise ValueError("invalid_global_cap")
        self.pricing = pricing
        self.phase_a_cap = phase_a_cap
        self.global_cap = global_cap
        self.charged = {"A": Decimal(0), "B": Decimal(0)}
        self.outstanding = None
        self.blocked = False
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o600)
        self.file = os.fdopen(descriptor, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file.seek(0)
            entries = [json.loads(line) for line in self.file]
            header = {
                "kind": "budget",
                "pricing": pricing.model_dump(mode="json"),
                "phase_a_cap": str(phase_a_cap),
                "global_cap": str(global_cap),
            }
            if entries:
                if entries[0] != header:
                    raise ValueError("budget_configuration_changed")
                for entry in entries[1:]:
                    if entry["kind"] == "reserve" and self.outstanding is None:
                        self.outstanding = (entry["phase"], Decimal(entry["reserved_usd"]))
                    elif entry["kind"] == "settle" and self.outstanding is not None:
                        phase, reserved = self.outstanding
                        usage = Usage.model_validate(entry["usage"]) if entry["usage"] else None
                        cost = pricing.cost(usage) if usage is not None else reserved
                        self.charged[phase] += cost
                        self.blocked |= usage is None or cost > reserved
                        self.outstanding = None
                    else:
                        raise ValueError("invalid_spend_journal")
            else:
                self._append(header)
        except BaseException:
            self.close()
            raise

    def _append(self, entry):
        self.file.write(json.dumps(entry) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())

    def reserve(self, phase: Literal["A", "B"], *, input_bound: int, output_bound: int):
        if self.outstanding is not None or self.blocked:
            raise ValueError("unresolved_submission")
        if phase not in self.charged or type(input_bound) is not int or input_bound < 1:
            raise ValueError("invalid_reservation")
        if type(output_bound) is not int or not 1 <= output_bound <= LIVE_MAX_OUTPUT_TOKENS:
            raise ValueError("invalid_reservation")
        cost = (
            input_bound * self.pricing.cache_write_usd_per_million
            + output_bound * self.pricing.output_usd_per_million
        ) / 1_000_000
        if sum(self.charged.values()) + cost > self.global_cap or (
            phase == "A" and self.charged["A"] + cost > self.phase_a_cap
        ):
            raise ValueError("budget_exhausted")
        self._append(
            {
                "kind": "reserve",
                "phase": phase,
                "reserved_usd": str(cost),
                "input_bound": input_bound,
                "output_bound": output_bound,
            }
        )
        self.outstanding = (phase, cost)
        return cost

    def settle(self, usage: Usage | None):
        if self.outstanding is None:
            raise ValueError("no_reservation")
        phase, reserved = self.outstanding
        cost = self.pricing.cost(usage) if usage is not None else reserved
        self._append({"kind": "settle", "usage": usage.model_dump() if usage else None})
        self.charged[phase] += cost
        self.outstanding = None
        self.blocked |= usage is None or cost > reserved
        if cost > reserved:
            raise ValueError("reservation_exceeded")
        return self.pricing.cost(usage) if usage is not None else None

    @property
    def upper_bound_usd(self):
        return sum(self.charged.values()) + (self.outstanding[1] if self.outstanding else 0)

    def close(self):
        self.file.close()
