"""Canonical classification only: no Telnyx wire parser, credentials or network."""

import sqlite3
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rj_studio_ai.config import Settings
from rj_studio_ai.domain import (
    AIReply,
    ChannelAvailability,
    ChannelAvailabilityChanged,
    ChannelLifecycleReason,
    ChannelScope,
    DeliveryStatus,
    DeliveryStatusReceived,
    EventOrigin,
    HumanMessageObserved,
    InboundMessage,
    InboundMessageReceived,
    MessageEdited,
    MessageReference,
    MessageRevoked,
    OutboundMessage,
    ProviderEventKind,
    ProviderEventMetadata,
    ProviderWebhookEventBatch,
    classify_provider_event,
)
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import SqliteConversationStore
from rj_studio_ai.providers.base import (
    ProviderAcceptance,
    ProviderWebhookResponse,
    WhatsAppProvider,
)
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def metadata(origin, event_id="event-synthetic"):
    return ProviderEventMetadata(event_id, origin, NOW)


def inbound():
    return InboundMessageReceived(
        "synthetic",
        "message-customer",
        "customer",
        "studio",
        "Texto sintético",
        metadata=metadata(EventOrigin.CUSTOMER),
    )


def human():
    return HumanMessageObserved(
        "synthetic",
        "message-human",
        "studio",
        "customer",
        metadata(EventOrigin.HUMAN_OPERATOR),
    )


def edit():
    return MessageEdited(
        "synthetic",
        "message-edit",
        "studio",
        "customer",
        MessageReference("synthetic", "message-customer"),
        metadata(EventOrigin.CUSTOMER),
    )


def revoke():
    return MessageRevoked(
        "synthetic",
        "message-revoke",
        "studio",
        "customer",
        MessageReference("upstream", "original-opaque"),
        metadata(EventOrigin.CUSTOMER),
    )


def lifecycle():
    return ChannelAvailabilityChanged(
        "synthetic",
        ChannelScope.ACCOUNT,
        "account-synthetic",
        ChannelAvailability.VERIFICATION_REQUIRED,
        ChannelLifecycleReason.RECONNECTED,
        metadata(EventOrigin.PROVIDER),
    )


def delivery_status():
    return DeliveryStatusReceived(
        "synthetic",
        "message-outbound",
        DeliveryStatus.DELIVERED,
        metadata=metadata(EventOrigin.PROVIDER),
        channel_id="studio",
        customer_address="customer",
    )


@pytest.mark.parametrize(
    ("make_event", "kind"),
    [
        (inbound, ProviderEventKind.CUSTOMER_MESSAGE),
        (human, ProviderEventKind.HUMAN_ACTIVITY),
        (edit, ProviderEventKind.MESSAGE_EDIT),
        (revoke, ProviderEventKind.MESSAGE_REVOCATION),
        (lifecycle, ProviderEventKind.CHANNEL_LIFECYCLE),
        (delivery_status, ProviderEventKind.DELIVERY_STATUS),
    ],
)
def test_classification_has_six_explicit_categories(make_event, kind):
    event = make_event()
    assert classify_provider_event(event) is kind
    assert isinstance(event, InboundMessage) == (kind is ProviderEventKind.CUSTOMER_MESSAGE)


@pytest.mark.parametrize("make_event", [human, edit, revoke, lifecycle])
def test_operational_events_have_no_text_that_can_become_an_ai_reply(make_event):
    event = make_event()
    assert not isinstance(event, (InboundMessage, AIReply))
    assert "body" not in {field.name for field in fields(event)}
    with pytest.raises(FrozenInstanceError):
        event.provider = "changed"


def test_envelope_identity_is_independent_of_message_identity_and_original_reference():
    first = edit()
    second = replace(first, metadata=replace(first.metadata, event_id="another-delivery-event"))
    assert first.metadata.event_id != second.metadata.event_id
    assert first.provider_message_id == second.provider_message_id == "message-edit"
    assert first.original_message == MessageReference("synthetic", "message-customer")
    assert revoke().original_message == MessageReference("upstream", "original-opaque")
    assert classify_provider_event(second) is ProviderEventKind.MESSAGE_EDIT


def test_alias_namespace_and_message_time_survive_without_changing_event_time():
    original_time = NOW - timedelta(minutes=2)
    event = replace(
        human(),
        metadata=replace(
            human().metadata,
            message_aliases=(MessageReference("upstream", "opaque-alias"),),
            message_occurred_at=original_time,
        ),
    )
    assert event.metadata.occurred_at == NOW
    assert event.metadata.message_occurred_at == original_time
    assert event.metadata.message_aliases == (MessageReference("upstream", "opaque-alias"),)
    assert event.provider_message_id == "message-human"
    assert classify_provider_event(event) is ProviderEventKind.HUMAN_ACTIVITY


@pytest.mark.parametrize("origin", [EventOrigin.HUMAN_OPERATOR, EventOrigin.PROVIDER])
def test_noncustomer_provenance_cannot_be_wrapped_as_inbound(origin):
    with pytest.raises(ValueError, match="origin does not match"):
        replace(inbound(), metadata=metadata(origin))


@pytest.mark.parametrize("make_event", [human, lifecycle, delivery_status])
def test_origin_mismatch_is_rejected_before_batch_ingress(make_event):
    with pytest.raises(ValueError, match="origin does not match"):
        replace(make_event(), metadata=metadata(EventOrigin.CUSTOMER))


@pytest.mark.parametrize("make_event", [edit, revoke])
def test_message_change_requires_original_identity_and_message_origin(make_event):
    with pytest.raises(ValueError, match="original Message reference"):
        replace(make_event(), original_message=None)
    with pytest.raises(ValueError, match="origin does not match"):
        replace(make_event(), metadata=metadata(EventOrigin.PROVIDER))


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": " "},
        {"origin": "customer"},
        {"occurred_at": None},
        {"occurred_at": NOW.replace(tzinfo=None)},
        {"message_occurred_at": NOW.replace(tzinfo=None)},
        {"message_aliases": [MessageReference("upstream", "alias")]},
        {"message_aliases": ("not-a-reference",)},
    ],
)
def test_invalid_provenance_fails_without_echoing_values(changes):
    with pytest.raises(ValueError, match="Canonical event"):
        replace(metadata(EventOrigin.CUSTOMER), **changes)


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "message.received",
        {"body": "ordinary text"},
        {"event_type": "message.echo", "body": "ordinary text"},
        {"event_type": "message.received", "body": {"type": "edit", "text": "edited"}},
        {"event_type": "message.received", "body": {"type": "revoke"}},
        SimpleNamespace(provider="synthetic", body="ordinary text"),
        ProviderAcceptance("message-outbound"),
        OutboundMessage("studio", "customer", "ordinary text"),
    ],
)
def test_unknown_objects_are_never_inferred_to_be_customer_input(invalid):
    with pytest.raises(ValueError, match="Unsupported canonical provider event"):
        classify_provider_event(invalid)


def test_unrecognized_inbound_subclass_is_not_silently_classified():
    class UnknownInbound(InboundMessageReceived):
        pass

    with pytest.raises(ValueError, match="Unsupported canonical provider event"):
        classify_provider_event(UnknownInbound("synthetic", "id", "customer", "studio", "text"))


@pytest.mark.parametrize("invalid", ["", " ", None])
def test_invalid_customer_text_is_not_classified_as_legitimate_inbound(invalid):
    with pytest.raises(ValueError, match="nonempty identifiers"):
        classify_provider_event(replace(inbound(), body=invalid))


def test_lifecycle_has_resource_scope_not_message_identity_or_sending_permission():
    event = lifecycle()
    assert event.scope is ChannelScope.ACCOUNT
    assert not hasattr(event, "provider_message_id")
    assert not hasattr(event, "customer_address")
    assert event.availability is ChannelAvailability.VERIFICATION_REQUIRED
    with pytest.raises(ValueError, match="cannot identify a Message"):
        replace(
            event,
            metadata=replace(
                event.metadata, message_aliases=(MessageReference("upstream", "not-an-account"),)
            ),
        )
    with pytest.raises(ValueError, match="Invalid canonical channel lifecycle"):
        replace(event, availability="active")


def test_acceptance_does_not_manufacture_delivery_confirmation():
    acceptance = ProviderAcceptance("message-outbound")
    assert not isinstance(acceptance, DeliveryStatusReceived)
    assert not hasattr(acceptance, "status")
    with pytest.raises(ValueError, match="Unsupported canonical provider event"):
        classify_provider_event(acceptance)
    with pytest.raises(ValueError, match="Invalid canonical delivery status"):
        classify_provider_event(replace(delivery_status(), status="accepted"))
    assert delivery_status().provider_message_id == acceptance.provider_message_id


def test_legacy_positional_constructors_and_missing_metadata_remain_valid():
    old = InboundMessage("synthetic", "id", "customer", "studio", "text")
    received = InboundMessageReceived("synthetic", "id", "customer", "studio", "text")
    status = DeliveryStatusReceived("synthetic", "outbound", DeliveryStatus.SENT, None)
    message = OutboundMessage("studio", "customer", "text")
    assert classify_provider_event(old) is ProviderEventKind.CUSTOMER_MESSAGE
    assert classify_provider_event(received) is ProviderEventKind.CUSTOMER_MESSAGE
    assert classify_provider_event(status) is ProviderEventKind.DELIVERY_STATUS
    assert received.metadata is status.metadata is message.submission_key is None
    assert ProviderWebhookEventBatch((received, status)).events == (received, status)
    keyed = replace(message, submission_key="stable-delivery-identity")
    sender = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("outbound")])
    assert sender.send(keyed, timeout_seconds=1).provider_message_id == "outbound"
    assert sender.calls[0][0].submission_key == "stable-delivery-identity"


@pytest.mark.parametrize("make_event", [human, edit, revoke, lifecycle])
def test_current_store_rejects_whole_unsupported_batch_before_admitting_customer(
    tmp_path, make_event
):
    path = tmp_path / "synthetic.db"
    store = SqliteConversationStore(path)
    store.initialize()
    with pytest.raises(ValueError, match="Unsupported canonical provider event"):
        store.record_webhook_events((inbound(), make_event()))
    with sqlite3.connect(path) as connection:
        for table in ("messages", "message_processing", "outbound_deliveries"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


class _CanonicalFixtureAdapter(WhatsAppProvider):
    """Returns typed fixtures; deliberately does not parse or authenticate a provider payload."""

    def __init__(self, event):
        self.event = event

    def receive(self, webhook):
        return ProviderWebhookEventBatch((self.event,))

    def is_configured(self):
        return True

    def acknowledge(self):
        return ProviderWebhookResponse("", "text/plain")

    def render_legacy_reply(self, reply):
        raise AssertionError("Operational activity must never render an AI Reply")


class _NoGeneration:
    def is_configured(self):
        return True

    def generate(self, *args, **kwargs):
        raise AssertionError("Operational activity must never reach generation")


@pytest.mark.parametrize("make_event", [human, edit, revoke, lifecycle])
@pytest.mark.parametrize("mode", ["legacy", "proactive"])
def test_runtime_never_autoresponds_to_unimplemented_operational_events(tmp_path, make_event, mode):
    path = tmp_path / "synthetic.db"
    store = SqliteConversationStore(path)
    sender = DeterministicFakeOutboundSender(outcomes=[])
    app = create_app(
        Settings(_env_file=None, database_path=path, delivery_mode=mode),
        provider=_CanonicalFixtureAdapter(make_event()),
        store=store,
        generator=_NoGeneration(),
        outbound_sender=sender,
    )
    # Proactive raises the existing unsupported-event error. No new handler is installed.
    with TestClient(app) as client:
        if mode == "proactive":
            with pytest.raises(ValueError, match="Unsupported canonical provider event"):
                client.post("/webhooks/whatsapp", json={})
        else:
            assert client.post("/webhooks/whatsapp", json={}).status_code == 400
    assert sender.calls == []
    assert store.list_pending_generations() == []
    assert store.get_history(provider="synthetic", customer_address="customer") == []
