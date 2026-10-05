"""Opt-in fence for smoke drivers; deliberately absent from normal app composition."""

import os
import re
from collections.abc import Mapping
from threading import Lock

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.providers.base import (
    OutboundMessageSender,
    OutboundPermanentError,
    ProviderAcceptance,
)


class LiveSmokeBlocked(OutboundPermanentError):
    """A safe operational code, never a recipient or credential value."""


class LiveSmokeOutboundSender(OutboundMessageSender):
    def __init__(
        self,
        *,
        provider: str,
        sender: OutboundMessageSender,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        configuration = os.environ if environment is None else environment
        if configuration.get("ALLOW_LIVE_MESSAGING_SMOKE") != "1":
            raise LiveSmokeBlocked("smoke_live_not_authorized")
        recipient = configuration.get("TEST_WHATSAPP_RECIPIENT", "")
        if not re.fullmatch(r"\+[1-9][0-9]{6,14}", recipient):
            raise LiveSmokeBlocked("smoke_test_recipient_required")
        if provider not in {"twilio", "meta"}:
            raise LiveSmokeBlocked("smoke_provider_invalid")
        self._recipient = "whatsapp:" + recipient if provider == "twilio" else recipient[1:]
        self._sender = sender
        self._lock = Lock()
        self._submitted = False

    def send(self, message: OutboundMessage, *, timeout_seconds: float) -> ProviderAcceptance:
        if message.recipient_address != self._recipient:
            raise LiveSmokeBlocked("smoke_recipient_mismatch")
        with self._lock:
            if self._submitted:
                raise LiveSmokeBlocked("smoke_submission_limit")
            # Reserve before external submission; never release on an ambiguous failure.
            self._submitted = True
        return self._sender.send(message, timeout_seconds=timeout_seconds)
