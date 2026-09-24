"""Durable in-process AI processing, separate from inbound HTTP acknowledgement."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from time import monotonic

from rj_studio_ai.application import MessageResponder, RetryableWebhookError
from rj_studio_ai.persistence import (
    GenerationClaimResult,
    GenerationRecoveryNotAvailable,
    SqliteConversationStore,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessingRunner:
    store: SqliteConversationStore
    responder: MessageResponder
    monotonic_clock: Callable[[], float] = monotonic
    _stop_acquisition: Event = field(init=False, default_factory=Event)
    _acquisition_gate: Lock = field(init=False, default_factory=Lock)

    def stop_acquiring(self) -> None:
        with self._acquisition_gate:
            self._stop_acquisition.set()

    def run_once(self) -> GenerationClaimResult | None:
        for candidate in self.store.list_pending_generations():
            if self._stop_acquisition.is_set():
                return None
            if candidate.blocked_by_predecessor:
                continue
            try:
                message = self.store.load_recoverable_inbound_message(
                    inbound_message_id=candidate.inbound_message_id
                )
            except GenerationRecoveryNotAvailable:
                continue
            with self._acquisition_gate:
                if self._stop_acquisition.is_set():
                    return None
                claim = self.store.claim_generation(message)
            try:
                reply = self.responder.process_persisted(
                    message,
                    monotonic_clock=self.monotonic_clock,
                    preclaimed=claim,
                )
            except RetryableWebhookError:
                return None
            if reply is None:
                continue
            lifecycle = self.store.get_generation(
                provider=message.provider,
                provider_message_id=message.provider_message_id,
            )
            if lifecycle is None:
                raise RuntimeError("Completed processing lifecycle is unavailable")
            return lifecycle
        return None


@dataclass(slots=True)
class ProcessingExecutor:
    runner: ProcessingRunner
    poll_interval_seconds: float
    concurrency: int
    on_completion: Callable[[], None] | None = None
    _stop: Event = field(init=False, default_factory=Event)
    _wake: Event = field(init=False, default_factory=Event)
    _failed: Event = field(init=False, default_factory=Event)
    _threads: list[Thread] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("Processing poll interval must be positive")
        if self.concurrency < 1:
            raise ValueError("Processing concurrency must be positive")

    def run_once(self) -> GenerationClaimResult | None:
        result = self.runner.run_once()
        if result is not None and self.on_completion is not None:
            self.on_completion()
        return result

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("Processing Executor has already started")
        for worker_number in range(self.concurrency):
            thread = Thread(
                target=self._run_worker,
                name=f"message-processing-{worker_number + 1}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self.runner.stop_acquiring()
        self._stop.set()
        self._wake.set()
        deadline = monotonic() + 11.0
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - monotonic()))

    def wake(self) -> None:
        self._wake.set()

    def is_alive(self) -> bool:
        return (
            bool(self._threads)
            and not self._failed.is_set()
            and all(thread.is_alive() for thread in self._threads)
        )

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.run_once()
            except Exception as error:
                logger.error(
                    "Message processing execution failed",
                    extra={"error_type": type(error).__name__},
                )
                self._failed.set()
                return
            if result is not None:
                continue
            self._wake.wait(self.poll_interval_seconds)
            self._wake.clear()
