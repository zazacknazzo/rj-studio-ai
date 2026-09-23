import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.persistence import (
    DeliveryState,
    OutboundDeliveryRecord,
    SqliteConversationStore,
)
from rj_studio_ai.providers.base import (
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    OutboundPermanentError,
    OutboundRetryableError,
)


class DeliveryOwnershipLost(RuntimeError):
    """Raised when a runner can no longer finalize its durable delivery claim."""


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OutboundDeliveryRunner:
    store: SqliteConversationStore
    sender: OutboundMessageSender
    timeout_seconds: float
    maximum_attempts: int = 3
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_maximum_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("Outbound timeout must be positive")
        if self.maximum_attempts < 1:
            raise ValueError("Outbound maximum attempts must be positive")
        if self.retry_backoff_base_seconds <= 0:
            raise ValueError("Outbound retry backoff must be positive")
        if self.retry_backoff_maximum_seconds < self.retry_backoff_base_seconds:
            raise ValueError("Outbound maximum backoff must cover the base backoff")

    def run_once(self, *, now: datetime | None = None) -> OutboundDeliveryRecord | None:
        claim = self.store.claim_next_delivery(now=now)
        if claim is None:
            return None
        if claim.owner_token is None:
            raise DeliveryOwnershipLost("Claimed Outbound Delivery has no owner")
        if not self.store.delivery_claim_is_current(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            now=now,
        ):
            raise DeliveryOwnershipLost("Outbound Delivery claim expired before submission")

        message = OutboundMessage(
            sender_address=claim.provider_channel_id,
            recipient_address=claim.recipient_address,
            body=claim.body,
        )
        try:
            acceptance = self.sender.send(message, timeout_seconds=self.timeout_seconds)
        except OutboundRetryableError:
            if claim.attempt_count >= self.maximum_attempts:
                self._finalize(
                    claim,
                    outcome=DeliveryState.FAILED,
                    safe_error_code="provider_retry_exhausted",
                    now=now,
                )
            else:
                current_time = now or datetime.now(UTC)
                backoff_seconds = min(
                    self.retry_backoff_base_seconds * (2 ** (claim.attempt_count - 1)),
                    self.retry_backoff_maximum_seconds,
                )
                self._finalize(
                    claim,
                    outcome=DeliveryState.RETRYABLE,
                    safe_error_code="provider_retryable",
                    retry_at=current_time + timedelta(seconds=backoff_seconds),
                    now=now,
                )
        except OutboundPermanentError:
            self._finalize(
                claim,
                outcome=DeliveryState.FAILED,
                safe_error_code="provider_permanent",
                now=now,
            )
        except OutboundOutcomeUnknown:
            self._finalize(
                claim,
                outcome=DeliveryState.UNKNOWN,
                safe_error_code="provider_outcome_unknown",
                now=now,
            )
        else:
            self._finalize(
                claim,
                outcome=DeliveryState.ACCEPTED,
                provider_message_id=acceptance.provider_message_id,
                now=now,
            )

        finalized = self.store.get_delivery(claim.delivery_id)
        if finalized is None:
            raise DeliveryOwnershipLost("Finalized Outbound Delivery is unavailable")
        return finalized

    def _finalize(
        self,
        claim: OutboundDeliveryRecord,
        *,
        outcome: DeliveryState,
        provider_message_id: str | None = None,
        safe_error_code: str | None = None,
        retry_at: datetime | None = None,
        now: datetime | None,
    ) -> None:
        if claim.owner_token is None:
            raise DeliveryOwnershipLost("Claimed Outbound Delivery has no owner")
        finalized = self.store.finalize_delivery(
            delivery_id=claim.delivery_id,
            owner_token=claim.owner_token,
            outcome=outcome,
            provider_message_id=provider_message_id,
            safe_error_code=safe_error_code,
            retry_at=retry_at,
            now=now,
        )
        if not finalized:
            raise DeliveryOwnershipLost("Outbound Delivery ownership changed during submission")


@dataclass(slots=True)
class OutboundDeliveryExecutor:
    """Lifespan-owned polling executor backed by durable delivery claims."""

    store: SqliteConversationStore
    sender: OutboundMessageSender
    request_timeout_seconds: float
    poll_interval_seconds: float
    concurrency: int
    maximum_attempts: int = 3
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_maximum_seconds: float = 30.0
    _stop: Event = field(init=False, default_factory=Event)
    _wake: Event = field(init=False, default_factory=Event)
    _threads: list[Thread] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        if self.request_timeout_seconds <= 0:
            raise ValueError("Outbound request timeout must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("Outbound polling interval must be positive")
        if self.concurrency < 1:
            raise ValueError("Outbound concurrency must be positive")
        OutboundDeliveryRunner(
            store=self.store,
            sender=self.sender,
            timeout_seconds=self.request_timeout_seconds,
            maximum_attempts=self.maximum_attempts,
            retry_backoff_base_seconds=self.retry_backoff_base_seconds,
            retry_backoff_maximum_seconds=self.retry_backoff_maximum_seconds,
        )

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("Outbound Delivery Executor has already started")
        for worker_number in range(self.concurrency):
            thread = Thread(
                target=self._run_worker,
                name=f"outbound-delivery-{worker_number + 1}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for thread in self._threads:
            thread.join(timeout=self.request_timeout_seconds + 1.0)

    def wake(self) -> None:
        self._wake.set()

    def is_alive(self) -> bool:
        return bool(self._threads) and all(thread.is_alive() for thread in self._threads)

    def _run_worker(self) -> None:
        runner = OutboundDeliveryRunner(
            store=self.store,
            sender=self.sender,
            timeout_seconds=self.request_timeout_seconds,
            maximum_attempts=self.maximum_attempts,
            retry_backoff_base_seconds=self.retry_backoff_base_seconds,
            retry_backoff_maximum_seconds=self.retry_backoff_maximum_seconds,
        )
        while not self._stop.is_set():
            try:
                result = runner.run_once()
            except Exception as error:
                logger.error(
                    "Outbound Delivery execution failed",
                    extra={"error_type": type(error).__name__},
                )
                result = None
            if result is not None:
                continue
            self._wake.wait(self.poll_interval_seconds)
            self._wake.clear()
