from dataclasses import dataclass
from datetime import datetime

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


@dataclass(slots=True)
class OutboundDeliveryRunner:
    store: SqliteConversationStore
    sender: OutboundMessageSender
    timeout_seconds: float

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("Outbound timeout must be positive")

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
            recipient_address=claim.recipient_address,
            body=claim.body,
        )
        try:
            acceptance = self.sender.send(message, timeout_seconds=self.timeout_seconds)
        except OutboundRetryableError:
            self._finalize(
                claim,
                outcome=DeliveryState.RETRYABLE,
                safe_error_code="provider_retryable",
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
            now=now,
        )
        if not finalized:
            raise DeliveryOwnershipLost("Outbound Delivery ownership changed during submission")
