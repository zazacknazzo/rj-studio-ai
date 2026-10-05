from concurrent.futures import ThreadPoolExecutor

import pytest

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.live_messaging_smoke import LiveSmokeBlocked, LiveSmokeOutboundSender
from rj_studio_ai.providers.base import OutboundOutcomeUnknown, ProviderAcceptance
from rj_studio_ai.providers.fake import DeterministicFakeOutboundSender


def test_live_smoke_default_off_blocks_before_any_submission():
    sender = DeterministicFakeOutboundSender(outcomes=[])
    with pytest.raises(LiveSmokeBlocked, match="smoke_live_not_authorized"):
        LiveSmokeOutboundSender(provider="twilio", sender=sender, environment={})
    assert sender.calls == []


@pytest.mark.parametrize("provider", ["twilio", "meta"])
def test_only_explicit_test_recipient_can_reach_sender(provider):
    sender = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("synthetic-id")])
    guard = LiveSmokeOutboundSender(
        provider=provider,
        sender=sender,
        environment={
            "ALLOW_LIVE_MESSAGING_SMOKE": "1",
            "TEST_WHATSAPP_RECIPIENT": "+5511000000001",
        },
    )
    with pytest.raises(LiveSmokeBlocked, match="smoke_recipient_mismatch"):
        guard.send(
            OutboundMessage("synthetic-channel", "persisted-last-customer", "Oi"), timeout_seconds=2
        )
    assert sender.calls == []
    recipient = "whatsapp:+5511000000001" if provider == "twilio" else "5511000000001"
    message = OutboundMessage("synthetic-channel", recipient, "Oi")
    assert guard.send(message, timeout_seconds=2) == ProviderAcceptance("synthetic-id")
    assert sender.calls == [(message, 2)]


@pytest.mark.parametrize("recipient", [None, "", " ", "last-customer", "whatsapp:+5511000000001"])
def test_explicit_canonical_test_recipient_required_without_fallback(recipient):
    environment = {"ALLOW_LIVE_MESSAGING_SMOKE": "1"}
    if recipient is not None:
        environment["TEST_WHATSAPP_RECIPIENT"] = recipient
    sender = DeterministicFakeOutboundSender(outcomes=[])
    with pytest.raises(LiveSmokeBlocked, match="smoke_test_recipient_required"):
        LiveSmokeOutboundSender(provider="twilio", sender=sender, environment=environment)
    assert sender.calls == []


@pytest.mark.parametrize("unknown", [False, True])
def test_guard_allows_one_submission_only_even_if_result_is_ambiguous(unknown):
    outcome = OutboundOutcomeUnknown("synthetic_ambiguous") if unknown else ProviderAcceptance("id")
    sender = DeterministicFakeOutboundSender(outcomes=[outcome, ProviderAcceptance("second")])
    guard = LiveSmokeOutboundSender(
        provider="meta",
        sender=sender,
        environment={
            "ALLOW_LIVE_MESSAGING_SMOKE": "1",
            "TEST_WHATSAPP_RECIPIENT": "+5511000000001",
        },
    )
    message = OutboundMessage("synthetic-channel", "5511000000001", "Oi")
    if unknown:
        with pytest.raises(OutboundOutcomeUnknown, match="synthetic_ambiguous"):
            guard.send(message, timeout_seconds=2)
    else:
        assert guard.send(message, timeout_seconds=2) == outcome
    with pytest.raises(LiveSmokeBlocked, match="smoke_submission_limit"):
        guard.send(message, timeout_seconds=2)
    assert len(sender.calls) == 1


def test_concurrent_smoke_submissions_cannot_escape_one_message_limit():
    sender = DeterministicFakeOutboundSender(outcomes=[ProviderAcceptance("id")])
    guard = LiveSmokeOutboundSender(
        provider="meta",
        sender=sender,
        environment={
            "ALLOW_LIVE_MESSAGING_SMOKE": "1",
            "TEST_WHATSAPP_RECIPIENT": "+5511000000001",
        },
    )

    def submit(_):
        try:
            return guard.send(
                OutboundMessage("synthetic-channel", "5511000000001", "Oi"), timeout_seconds=2
            )
        except LiveSmokeBlocked:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results.count(ProviderAcceptance("id")) == 1
    assert results.count(None) == 1
    assert len(sender.calls) == 1


@pytest.mark.parametrize("flag", ["0", "true", "yes", " 1 ", ""])
def test_opt_in_is_exact_and_errors_are_safe(flag):
    sender = DeterministicFakeOutboundSender(outcomes=[])
    environment = {
        "ALLOW_LIVE_MESSAGING_SMOKE": flag,
        "TEST_WHATSAPP_RECIPIENT": "+5511000000001",
        "TWILIO_AUTH_TOKEN": "synthetic-private-token",
    }
    with pytest.raises(LiveSmokeBlocked) as error:
        LiveSmokeOutboundSender(provider="twilio", sender=sender, environment=environment)
    assert str(error.value) == "smoke_live_not_authorized"
    assert sender.calls == []


def test_guard_repr_does_not_include_recipient_or_unrelated_secrets():
    sender = DeterministicFakeOutboundSender(outcomes=[])
    guard = LiveSmokeOutboundSender(
        provider="meta",
        sender=sender,
        environment={
            "ALLOW_LIVE_MESSAGING_SMOKE": "1",
            "TEST_WHATSAPP_RECIPIENT": "+5511000000001",
            "META_WHATSAPP_ACCESS_TOKEN": "synthetic-private-token",
        },
    )
    assert "5511000000001" not in repr(guard)
    assert "synthetic-private-token" not in repr(guard)


def test_missing_real_environment_flag_cannot_use_a_recipient_fallback(monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE_MESSAGING_SMOKE", raising=False)
    monkeypatch.setenv("TEST_WHATSAPP_RECIPIENT", "+5511000000001")
    with pytest.raises(LiveSmokeBlocked, match="smoke_live_not_authorized"):
        LiveSmokeOutboundSender(
            provider="meta", sender=DeterministicFakeOutboundSender(outcomes=[])
        )
