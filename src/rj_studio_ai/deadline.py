from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ExecutionDeadline:
    """One monotonic budget shared by every stage of a webhook execution."""

    DEFAULT_TOTAL_SECONDS: ClassVar[float] = 10.0
    DEFAULT_FINALIZATION_MARGIN_SECONDS: ClassVar[float] = 1.0

    _expires_at: float
    _finalization_margin_seconds: float
    _clock: Callable[[], float]

    @classmethod
    def start(
        cls,
        *,
        clock: Callable[[], float] = monotonic,
        total_seconds: float = DEFAULT_TOTAL_SECONDS,
        finalization_margin_seconds: float = DEFAULT_FINALIZATION_MARGIN_SECONDS,
    ) -> "ExecutionDeadline":
        if total_seconds <= 0:
            raise ValueError("Deadline total must be positive")
        if not 0 <= finalization_margin_seconds < total_seconds:
            raise ValueError("Finalization margin must fit inside the deadline")
        return cls(
            _expires_at=clock() + total_seconds,
            _finalization_margin_seconds=finalization_margin_seconds,
            _clock=clock,
        )

    def remaining_budget(self) -> float:
        return max(0.0, self._expires_at - self._clock())

    def work_budget(self) -> float:
        return max(0.0, self.remaining_budget() - self._finalization_margin_seconds)

    def is_expired(self) -> bool:
        return self.remaining_budget() <= 0.0
