"""Offline ingress composition. No route, executor, LLM or sender is started here."""

from datetime import datetime

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import ProviderWebhookRequest, ProviderWebhookResponse
from rj_studio_ai.providers.telnyx_messages import TelnyxMessageAdapter


def receive_telnyx_messages(
    requests: tuple[ProviderWebhookRequest, ...],
    *,
    adapter: TelnyxMessageAdapter,
    store: SqliteConversationStore,
    deadline: ExecutionDeadline,
    now: datetime | None = None,
) -> ProviderWebhookResponse:
    """Authenticate every envelope, commit one batch, then acknowledge.

    The tuple is a local composition/testing boundary, not a claimed Telnyx wire
    batch format. The production route and streaming/raw-header gates are Ticket 12.
    """
    if not requests or len(requests) > 100:
        raise ValueError("Invalid ingress batch size")
    events = []
    for request in requests:
        if deadline.is_expired():
            raise PersistenceUnavailable("Webhook ingress deadline expired")
        events.extend(adapter.receive(request).events)
    store.record_webhook_events(
        tuple(events), now=now, deadline=deadline, require_message_provenance=True
    )
    if deadline.is_expired():
        # Commit may have completed as the budget elapsed; replay is durable/idempotent.
        raise PersistenceUnavailable("Webhook ingress deadline expired")
    return adapter.acknowledge()
