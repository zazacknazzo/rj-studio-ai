"""Eval-only latency evidence; diagnostics never replace the product gate."""

import math
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from unittest.mock import patch

from pydantic import model_validator

from rj_studio_ai.evaluation.records import (
    PRODUCT_E2E_LATENCY_LIMIT_MS,
    Milliseconds,
    RecordModel,
    percentile,
)

COMPONENTS = (
    "admission_ms",
    "input_count_ms",
    "budget_reservation_ms",
    "model_request_ms",
    "decision_validation_ms",
    "trusted_finalization_ms",
    "persistence_ms",
    "fake_outbound_ms",
    "eval_bookkeeping_ms",
)
EVAL_ONLY_COMPONENTS = ("input_count_ms", "budget_reservation_ms", "eval_bookkeeping_ms")
RECONCILIATION_TOLERANCE_MS = 1.0


class LatencyBreakdown(RecordModel):
    admission_ms: Milliseconds | None
    input_count_ms: Milliseconds | None
    budget_reservation_ms: Milliseconds | None
    model_request_ms: Milliseconds | None
    decision_validation_ms: Milliseconds | None
    trusted_finalization_ms: Milliseconds | None
    persistence_ms: Milliseconds | None
    fake_outbound_ms: Milliseconds | None
    eval_bookkeeping_ms: Milliseconds | None
    unattributed_ms: Milliseconds | None
    observed_eval_e2e_ms: Milliseconds | None
    production_equivalent_e2e_ms: Milliseconds | None

    @model_validator(mode="after")
    def reconcile(self):
        values = [getattr(self, name) for name in COMPONENTS]
        observed = self.observed_eval_e2e_ms
        diagnostic = self.production_equivalent_e2e_ms
        if observed is None or self.unattributed_ms is None:
            if diagnostic is not None:
                raise ValueError("latency_diagnostic_missing_evidence")
            return self
        if any(v is None for v in values) and diagnostic is not None:
            raise ValueError("latency_diagnostic_missing_evidence")
        if not math.isclose(
            sum(v for v in values if v is not None) + self.unattributed_ms,
            observed,
            abs_tol=RECONCILIATION_TOLERANCE_MS,
            rel_tol=0,
        ):
            raise ValueError("latency_components_do_not_reconcile")
        if all(v is not None for v in values) and (
            diagnostic is None
            or not math.isclose(
                diagnostic,
                observed - sum(getattr(self, name) for name in EVAL_ONLY_COMPONENTS),
                abs_tol=RECONCILIATION_TOLERANCE_MS,
                rel_tol=0,
            )
        ):
            raise ValueError("latency_diagnostic_mismatch")
        return self


@dataclass
class _Interval:
    started: float
    nested_seconds: float = 0.0
    elapsed_ms: float | None = None


class LatencyRecorder:
    """Exclusive, allowlisted durations for one serial synthetic eval execution."""

    def __init__(self, *, clock):
        self.clock = clock
        self.values = dict.fromkeys(COMPONENTS)
        self._stack = []

    @contextmanager
    def measure(self, component):
        if component not in self.values:
            raise ValueError("latency_unknown_component")
        frame = _Interval(self.clock())
        self._stack.append(frame)
        try:
            yield frame
        finally:
            elapsed = self.clock() - frame.started
            self._stack.pop()
            exclusive = elapsed - frame.nested_seconds
            if elapsed < 0 or exclusive < -0.000001:
                raise ValueError("latency_clock_regressed")
            frame.elapsed_ms = max(0, exclusive) * 1000
            self.values[component] = (self.values[component] or 0.0) + frame.elapsed_ms
            if self._stack:
                self._stack[-1].nested_seconds += elapsed

    def finish(self, observed_ms):
        remaining = observed_ms - sum(v for v in self.values.values() if v is not None)
        if remaining < -RECONCILIATION_TOLERANCE_MS:
            raise ValueError("latency_components_do_not_reconcile")
        diagnostic = None
        if all(v is not None for v in self.values.values()):
            diagnostic = observed_ms - sum(self.values[name] for name in EVAL_ONLY_COMPONENTS)
        return LatencyBreakdown(
            **self.values,
            unattributed_ms=max(0, remaining),
            observed_eval_e2e_ms=observed_ms,
            production_equivalent_e2e_ms=diagnostic,
        )


@contextmanager
def observe_store(store, timing):
    """Observe only this eval store instance; preserve every production method."""
    with ExitStack() as stack:
        for name, component in (
            ("admit_generation", "admission_ms"),
            ("claim_generation", "admission_ms"),
            ("record_generation_metric", "persistence_ms"),
            ("complete_generation", "persistence_ms"),
            ("mark_generation_retryable", "persistence_ms"),
        ):
            method = getattr(store, name)

            def observed(*args, _method=method, _component=component, **kwargs):
                with timing.measure(_component):
                    return _method(*args, **kwargs)

            stack.enter_context(patch.object(store, name, observed))
        yield


def summarize_latency(samples):
    population = [sample for sample in samples if sample.attempts]
    components = {}
    for name in (
        *COMPONENTS,
        "unattributed_ms",
        "observed_eval_e2e_ms",
        "production_equivalent_e2e_ms",
    ):
        observed = [
            getattr(sample.latency_breakdown, name)
            for sample in population
            if sample.latency_breakdown is not None
            and getattr(sample.latency_breakdown, name) is not None
        ]
        components[name] = {
            "observed_n": len(observed),
            "missing_n": len(population) - len(observed),
            "p50_ms": percentile(observed, 0.5),
            "p95_ms": percentile(observed, 0.95),
            "max_ms": max(observed) if observed else None,
            "above_8s_n": sum(value > PRODUCT_E2E_LATENCY_LIMIT_MS for value in observed),
        }
    return {
        "population": "executions_with_generation_attempts",
        "execution_count": len(population),
        "diagnostic_status": "not_an_operational_gate",
        "components": components,
    }
