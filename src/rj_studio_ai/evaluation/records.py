"""Offline eval evidence: strict allowlists, independently recomputed denominators/costs."""

import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

Count = Annotated[int, Field(strict=True, ge=0)]
PositiveCount = Annotated[int, Field(strict=True, gt=0)]
Milliseconds = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,99}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Metric = Literal["grounding", "intent", "handoff", "persona", "context"]
Verdict = Literal["pass", "fail", "not_run"]
PRODUCT_E2E_LATENCY_LIMIT_MS = 8000


def check_privacy(value: object) -> None:
    """Defense in depth. Allowlists/provenance remain primary; regex cannot prove sanitization."""
    if isinstance(value, dict):
        for key, child in value.items():
            check_privacy(str(key))
            if isinstance(child, str) and (
                (
                    key in {"suite", "knowledge", "prompt", "reply_hash", "oracle"}
                    and re.fullmatch(r"[a-f0-9]{64}", child)
                )
                or (key == "revision" and re.fullmatch(r"[a-f0-9]{7,40}", child))
                or (key == "run_id" and re.fullmatch(r"[a-f0-9]{32}", child))
            ):
                continue
            check_privacy(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            check_privacy(child)
        return
    if not isinstance(value, str):
        return
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:T|$)", value):
        try:
            datetime.fromisoformat(value)
            return
        except ValueError:
            pass
    serialized = value
    patterns = (
        r"(?i)\b(?:sk-|sk_live_|Bearer\s|Authorization\s*[:=])",
        r"(?i)\b(?:AC|SK|SM)[a-f0-9]{32}\b",
        r"(?i)\b(?:api[_ -]?key|auth[_ -]?token|access[_ -]?token|password|secret)\b",
        r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}",
        r"\bEAA[a-zA-Z0-9]{20,}\b",
        r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b",
    )
    if any(re.search(pattern, serialized) for pattern in patterns):
        raise ValueError("eval_privacy_violation")
    if re.fullmatch(r"[a-fA-F0-9]{32,64}", serialized):
        raise ValueError("eval_unexpected_credential_shaped_metadata")
    if any(
        sum(character.isdigit() for character in match) >= 10
        for match in re.findall(r"\+?\d[\d ().-]{8,}\d", serialized)
    ):
        raise ValueError("eval_privacy_violation")


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


class RecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelConfiguration(RecordModel):
    provider: Identifier
    model: Identifier
    thinking: Literal["disabled"]
    structured_output: StrictBool
    max_output_tokens: PositiveCount
    context_max_messages: PositiveCount
    context_token_budget: PositiveCount


class Fingerprints(RecordModel):
    suite: Digest
    knowledge: Digest
    prompt: Digest


class Pricing(RecordModel):
    """Rates require explicit provenance. Synthetic rates never authorize a live gate."""

    version: Identifier
    status: Literal["unapproved", "synthetic", "approved"]
    provider: Identifier
    model: Identifier
    source: str = Field(min_length=1, max_length=300)
    input_usd_per_million: Decimal | None
    output_usd_per_million: Decimal | None
    reviewed_at: date | None = None
    approved_by: Identifier | None = None

    @model_validator(mode="after")
    def valid_rates(self):
        for rate in (self.input_usd_per_million, self.output_usd_per_million):
            if rate is not None and (not rate.is_finite() or rate < 0):
                raise ValueError("eval_invalid_pricing")
        if self.status != "unapproved" and (
            self.input_usd_per_million is None or self.output_usd_per_million is None
        ):
            raise ValueError("eval_missing_pricing")
        if self.status == "approved" and (
            self.reviewed_at is None
            or self.approved_by is None
            or not self.source.startswith("https://")
        ):
            raise ValueError("eval_missing_pricing_approval")
        check_privacy(self.model_dump(mode="json"))
        return self


class CheckContract(RecordModel):
    metric: Metric
    critical: StrictBool = False


class CaseContract(RecordModel):
    case_id: Identifier
    turns: PositiveCount
    checks: dict[Identifier, CheckContract] = Field(min_length=1)


class Attempt(RecordModel):
    number: PositiveCount
    outcome: Literal["success", "failure"]
    billable: StrictBool | None
    input_tokens: Count | None
    output_tokens: Count | None
    latency_ms: Milliseconds
    error_code: Identifier | None = None

    @model_validator(mode="after")
    def failure_has_safe_code(self):
        if (self.outcome == "failure") != (self.error_code is not None):
            raise ValueError("eval_invalid_attempt_outcome")
        return self


class Sample(RecordModel):
    case_id: Identifier
    repetition: PositiveCount
    turn: PositiveCount
    status: Literal["completed", "observed", "suppressed", "failed"]
    reply_hash: Digest | None
    attempts: tuple[Attempt, ...]
    e2e_latency_ms: Milliseconds | None
    ingress_latency_ms: Milliseconds | None = None
    queue_latency_ms: Milliseconds | None = None
    processing_latency_ms: Milliseconds | None = None
    outbound_latency_ms: Milliseconds | None = None
    checks: dict[Identifier, Verdict]

    @model_validator(mode="after")
    def logical_reply_and_attempts(self):
        if (self.status == "completed" and self.reply_hash is None) or (
            self.status in {"suppressed", "failed"} and self.reply_hash is not None
        ):
            raise ValueError("eval_invalid_reply_count")
        if [attempt.number for attempt in self.attempts] != list(range(1, len(self.attempts) + 1)):
            raise ValueError("eval_invalid_attempt_sequence")
        return self


class Ratio(RecordModel):
    numerator: Count
    denominator: Count

    @model_validator(mode="after")
    def valid_fraction(self):
        if self.numerator > self.denominator:
            raise ValueError("eval_invalid_denominator")
        return self


class Summary(RecordModel):
    run_count: PositiveCount
    completed_replies: Count
    billable_retries: Count
    token_consuming_failures: Count
    unknown_billing_attempts: Count
    input_tokens: Count | None
    output_tokens: Count | None
    model_p50_ms: Milliseconds | None
    model_p95_ms: Milliseconds | None
    e2e_p50_ms: Milliseconds | None
    e2e_p95_ms: Milliseconds | None
    billable_e2e_p50_ms: Milliseconds | None
    billable_e2e_p95_ms: Milliseconds | None
    estimated_cost_usd: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)] | None
    cost_per_1000_replies_usd: (
        Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)] | None
    )
    critical_failures: Ratio
    metrics: dict[Metric, Ratio]


def percentile(values: list[float], fraction: float) -> float | None:
    """Linear interpolation (R7): index (n-1)*p. Empty populations are unknown."""
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def summarize(samples, contracts, pricing=None, *, run_count=1) -> Summary:
    """Every attempt contributes; retries do not create another logical completed reply."""
    samples = [s if isinstance(s, Sample) else Sample.model_validate(s) for s in samples]
    contracts = [
        c if isinstance(c, CaseContract) else CaseContract.model_validate(c) for c in contracts
    ]
    if pricing is not None and not isinstance(pricing, Pricing):
        pricing = Pricing.model_validate(pricing)
    by_case = {contract.case_id: contract for contract in contracts}
    attempts = [attempt for sample in samples for attempt in sample.attempts]
    model_latencies = [attempt.latency_ms for attempt in attempts]
    e2e_latencies = [s.e2e_latency_ms for s in samples if s.e2e_latency_ms is not None]
    billable_e2e_latencies = [
        s.e2e_latency_ms
        for s in samples
        if s.e2e_latency_ms is not None and any(a.billable is True for a in s.attempts)
    ]
    completed = sum(sample.status == "completed" for sample in samples)
    cost = Decimal(0) if pricing is not None and pricing.status != "unapproved" else None
    for attempt in attempts:
        if attempt.billable is None or (
            attempt.billable and (attempt.input_tokens is None or attempt.output_tokens is None)
        ):
            cost = None
        if cost is not None and attempt.billable:
            cost += (
                Decimal(attempt.input_tokens) * pricing.input_usd_per_million
                + Decimal(attempt.output_tokens) * pricing.output_usd_per_million
            ) / Decimal(1_000_000)
    metrics = {}
    critical_failures = critical_count = 0
    for sample in samples:
        for identifier, check in by_case[sample.case_id].checks.items():
            verdict = sample.checks[identifier]
            ratio = metrics.setdefault(check.metric, [0, 0])
            ratio[0] += verdict == "pass"
            ratio[1] += 1
            if check.critical:
                critical_count += 1
                # not_run is fail-closed, never silently removed from the denominator.
                critical_failures += verdict != "pass"
    totals = {}
    for name in ("input_tokens", "output_tokens"):
        values = [getattr(attempt, name) for attempt in attempts]
        totals[name] = sum(values) if all(value is not None for value in values) else None
    return Summary(
        run_count=run_count,
        completed_replies=completed,
        billable_retries=sum(a.billable is True and a.number > 1 for a in attempts),
        token_consuming_failures=sum(
            a.outcome == "failure" and bool((a.input_tokens or 0) + (a.output_tokens or 0))
            for a in attempts
        ),
        unknown_billing_attempts=sum(a.billable is None for a in attempts),
        **totals,
        model_p50_ms=percentile(model_latencies, 0.5),
        model_p95_ms=percentile(model_latencies, 0.95),
        e2e_p50_ms=percentile(e2e_latencies, 0.5),
        e2e_p95_ms=percentile(e2e_latencies, 0.95),
        billable_e2e_p50_ms=percentile(billable_e2e_latencies, 0.5),
        billable_e2e_p95_ms=percentile(billable_e2e_latencies, 0.95),
        estimated_cost_usd=float(cost) if cost is not None else None,
        cost_per_1000_replies_usd=float(cost * 1000 / completed)
        if cost is not None and completed
        else None,
        critical_failures=Ratio(numerator=critical_failures, denominator=critical_count),
        metrics={metric: Ratio(numerator=n, denominator=d) for metric, (n, d) in metrics.items()},
    )


class RunRecord(RecordModel):
    schema_version: Literal[1]
    run_id: Identifier
    suite_id: Literal["v1"]
    mode: Literal["deterministic", "live_import"]
    status: Literal["completed", "incomplete"]
    created_at: datetime
    revision: Annotated[str, Field(pattern=r"^[a-f0-9]{7,40}$")]
    configuration: ModelConfiguration
    fingerprints: Fingerprints
    repetitions: PositiveCount
    total_cases: PositiveCount
    contracts: tuple[CaseContract, ...]
    pricing: Pricing | None
    samples: tuple[Sample, ...]
    summary: Summary
    rubric_version: Literal["livia-naturalness-v1"] = "livia-naturalness-v1"
    naturalness_status: Literal["pending_human_review"] = "pending_human_review"
    latency_scope: Literal["offline_policy", "inbound_persistence_to_provider_acceptance"] = (
        "offline_policy"
    )

    @model_validator(mode="after")
    def validate_evidence(self):
        check_privacy(self.model_dump(mode="json"))
        if self.created_at.tzinfo is None:
            raise ValueError("eval_missing_timezone")
        if self.mode == "live_import" and self.configuration.provider == "deterministic":
            raise ValueError("eval_synthetic_live_evidence")
        if self.mode == "deterministic" and self.latency_scope != "offline_policy":
            raise ValueError("eval_synthetic_latency_scope")
        contracts = {contract.case_id: contract for contract in self.contracts}
        if len(contracts) != len(self.contracts) or self.total_cases != len(contracts):
            raise ValueError("eval_invalid_case_count")
        expected = {
            (c.case_id, rep, turn)
            for c in self.contracts
            for rep in range(1, self.repetitions + 1)
            for turn in range(1, c.turns + 1)
        }
        observed = {(s.case_id, s.repetition, s.turn) for s in self.samples}
        if len(observed) != len(self.samples) or observed != expected:
            raise ValueError("eval_missing_or_duplicate_sample")
        for sample in self.samples:
            if sample.checks.keys() != contracts[sample.case_id].checks.keys():
                raise ValueError("eval_missing_check")
            if self.mode == "live_import" and sample.status == "completed" and not sample.attempts:
                raise ValueError("eval_missing_generation_evidence")
            if self.latency_scope == "inbound_persistence_to_provider_acceptance" and (
                sample.e2e_latency_ms is not None
                and sample.e2e_latency_ms < sum(a.latency_ms for a in sample.attempts)
            ):
                raise ValueError("eval_attempt_latency_omitted")
        if self.summary != summarize(self.samples, self.contracts, self.pricing):
            raise ValueError("eval_summary_mismatch")
        if self.status == "completed" and any(
            verdict == "not_run" for s in self.samples for verdict in s.checks.values()
        ):
            raise ValueError("eval_incomplete_checks")
        if self.pricing is not None and (
            self.pricing.provider != self.configuration.provider
            or self.pricing.model != self.configuration.model
        ):
            raise ValueError("eval_pricing_model_mismatch")
        return self

    def gates(self) -> dict[str, str]:
        safety = (
            "pass"
            if (
                self.summary.critical_failures.denominator > 0
                and self.summary.critical_failures.numerator == 0
            )
            else "fail"
        )
        if self.mode == "deterministic":
            return {"safety": safety, "latency": "pending_live", "cost": "pending_live"}
        if self.status != "completed":
            return {"safety": safety, "latency": "pending_evidence", "cost": "pending_evidence"}
        complete_latency = (
            self.latency_scope == "inbound_persistence_to_provider_acceptance"
            and not self.summary.unknown_billing_attempts
            and all(
                s.e2e_latency_ms is not None
                for s in self.samples
                if any(a.billable is True for a in s.attempts)
            )
        )
        latency = "pending_evidence"
        if complete_latency and self.summary.billable_e2e_p95_ms is not None:
            latency = (
                "pass"
                if self.summary.billable_e2e_p95_ms <= PRODUCT_E2E_LATENCY_LIMIT_MS
                else "fail"
            )
        cost = "pending_pricing"
        if (
            self.pricing is not None
            and self.pricing.status == "approved"
            and self.summary.cost_per_1000_replies_usd is not None
        ):
            cost = "pass" if self.summary.cost_per_1000_replies_usd <= 10 else "fail"
        return {"safety": safety, "latency": latency, "cost": cost}
