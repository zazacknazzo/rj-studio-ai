"""Signed direct-message admission and canonical replies to previously unknown contacts."""

import pytest
from test_waha_b1 import CHANNEL, KEY, SECONDARY, envelope, request

from rj_studio_ai.persistence import DeliveryState
from rj_studio_ai.providers.waha import WahaAdapter

pytest_plugins = ("test_waha_private_test",)

NEW = "15550000009@c.us"
LID = "777123456789@lid"


def open_adapter():
    return WahaAdapter(secret=KEY, secondary=SECONDARY, participants=(), all_direct=True)


@pytest.mark.parametrize("sender", [NEW, LID])
def test_new_signed_direct_sender_is_admitted(sender):
    a = open_adapter()
    raw = envelope()
    raw["payload"].update({"from": sender, "id": "false_" + sender + "_ONE"})
    event = a.receive(request(raw)).events[0]
    assert event.customer_address == sender
    assert a.reply_aliases(sender)[sender] == sender


@pytest.mark.parametrize(
    "sender",
    [CHANNEL, "123@g.us", "status@broadcast", "123@newsletter", "other", None],
)
def test_open_audience_still_rejects_self_and_non_direct_addresses(sender):
    raw = envelope()
    raw["payload"].update({"from": sender, "id": "false_" + str(sender) + "_ONE"})
    assert open_adapter().receive(request(raw)).events == ()


def test_self_lid_and_echo_are_ignored():
    a = open_adapter()
    a.bind_verified_identities({"999@lid": CHANNEL})
    for sender, from_me in [("999@lid", False), (NEW, True)]:
        raw = envelope()
        raw["payload"].update({"from": sender, "fromMe": from_me, "id": "false_" + sender + "_ONE"})
        assert a.receive(request(raw)).events == ()


@pytest.mark.parametrize("live", ["all_direct"], indirect=True)
def test_two_unknown_contacts_have_isolated_memory_and_no_duplicate_send(live):
    _, _, store, authority, _, delivery, inbound, posts, _, context = live
    first = inbound("FIRST", "Oi", sender=NEW)
    assert delivery.run_once().state is DeliveryState.ACCEPTED
    second = inbound("SECOND", "Oi", sender=LID)
    assert delivery.run_once().state is DeliveryState.ACCEPTED
    store.record_webhook_events((first,), require_message_provenance=True)
    assert delivery.run_once() is None
    later = inbound("THIRD", "Quanto custa?", sender=NEW)
    state = store.get_generation(provider="waha", provider_message_id=later.provider_message_id)
    built = context.build(inbound_message_id=state.inbound_message_id, current_body="Quanto custa?")
    assert sum(t.role == "customer" for t in built.history) == 1
    assert any(t.role == "ai_attendant" for t in built.history)
    assert delivery.run_once().state is DeliveryState.ACCEPTED
    assert [p["chatId"] for p in posts] == [NEW, LID, NEW]
    assert first.customer_address != second.customer_address
    assert len(authority.current()["intents"]) == 3


@pytest.mark.parametrize("live", ["all_direct"], indirect=True)
def test_unknown_for_one_contact_blocks_all_contacts(live):
    _, _, _, _, _, delivery, inbound, posts, outcome, _ = live
    outcome["value"] = "timeout"
    inbound("ONE", sender=NEW)
    assert delivery.run_once().state is DeliveryState.UNKNOWN
    inbound("TWO", sender=LID)
    assert delivery.run_once() is None
    assert len(posts) == 1


@pytest.mark.parametrize("live", ["all_direct"], indirect=True)
def test_revoked_contact_cannot_obtain_grant(live):
    _, journal, _, authority, _, delivery, inbound, posts, _, _ = live
    inbound(sender=NEW)
    journal.change("revoke", NEW)
    journal.change("resume")
    authority.activate()
    assert delivery.run_once() is None
    assert not authority.permits_participant(authority.current(), authority.current()["revoked"][0])
    assert posts == []


@pytest.mark.parametrize("live", ["all_direct"], indirect=True)
def test_open_audience_cannot_send_without_a_persisted_reply(live):
    from rj_studio_ai.domain import OutboundMessage
    from rj_studio_ai.providers.base import OutboundOutcomeUnknown

    _, _, _, _, _, delivery, _, posts, _, _ = live
    with pytest.raises(OutboundOutcomeUnknown):
        delivery.sender.send(
            OutboundMessage(CHANNEL, NEW, "Oi", submission_key="unclaimed"),
            timeout_seconds=1,
        )
    assert posts == []
