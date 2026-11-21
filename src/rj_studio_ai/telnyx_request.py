"""Exact offline WhatsApp request and private, keyed durable integrity binding."""

import hashlib
import hmac
import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from uuid import UUID

from rj_studio_ai.domain import OutboundMessage


class InvalidTelnyxRequest(ValueError):
    """Fixed local error; never include payload or configuration values."""


def _validate(message: OutboundMessage) -> None:
    try:
        key = UUID(message.submission_key)
        valid = key.version == 4 and str(key) == message.submission_key
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not (
        valid
        and re.fullmatch(r"\+[1-9][0-9]{6,14}", message.sender_address)
        and re.fullmatch(r"\+[1-9][0-9]{6,14}", message.recipient_address)
        and isinstance(message.body, str)
        and message.body.strip()
    ):
        raise InvalidTelnyxRequest("Invalid offline Telnyx request")


def _profile_valid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except (TypeError, ValueError, AttributeError):
        return False


def _body(message: OutboundMessage, profile_id: str) -> bytes:
    return json.dumps(
        {
            "from": message.sender_address,
            "to": message.recipient_address,
            "type": "WHATSAPP",
            "messaging_profile_id": profile_id,
            "whatsapp_message": {
                "type": "text",
                "text": {"body": message.body, "preview_url": False},
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class TelnyxRequest:
    message: OutboundMessage
    organization_id: str
    profile_id: str
    content: bytes
    integrity_key_id: str
    request_mac: str
    method: str = "POST"
    scheme: str = "https"
    host: str = "api.telnyx.com"
    path: str = "/v2/messages/whatsapp"
    query: bytes = b""
    content_type: str = "application/json"
    version: str = "t11-v1"

    @property
    def headers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Content-Type", self.content_type),
            ("Idempotency-Key", self.message.submission_key),
        )

    def canonical_for(self, message: OutboundMessage) -> bool:
        try:
            _validate(message)
            return (
                self.message == message
                and _profile_valid(self.profile_id)
                and self.method == "POST"
                and self.scheme == "https"
                and self.host == "api.telnyx.com"
                and self.path == "/v2/messages/whatsapp"
                and self.query == b""
                and self.content_type == "application/json"
                and self.version == "t11-v1"
                and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.integrity_key_id))
                and bool(re.fullmatch(r"[0-9a-f]{64}", self.request_mac))
                and self.content == _body(message, self.profile_id)
            )
        except (ValueError, TypeError, UnicodeError):
            return False

    def integrity_input(self) -> bytes:
        metadata = json.dumps(
            [
                self.version,
                self.integrity_key_id,
                self.organization_id,
                self.profile_id,
                self.method,
                self.scheme,
                self.host,
                self.path,
                self.query.hex(),
                self.content_type,
                self.message.submission_key,
                "free_form",
                "text",
                self.message.sender_address,
                self.message.recipient_address,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return metadata + b"\x00" + self.content


@dataclass(frozen=True, slots=True, repr=False)
class TelnyxRequestSigner:
    organization_id: str
    profile_id: str
    integrity_key_id: str
    integrity_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not (
            isinstance(self.integrity_key, bytes)
            and len(self.integrity_key) >= 32
            and _profile_valid(self.profile_id)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.integrity_key_id)
            and all(
                isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,255}", v)
                for v in (self.organization_id, self.profile_id)
            )
        ):
            raise InvalidTelnyxRequest("Invalid offline Telnyx integrity configuration")

    def prepare(self, message: OutboundMessage) -> TelnyxRequest:
        _validate(message)
        try:
            request = TelnyxRequest(
                message,
                self.organization_id,
                self.profile_id,
                _body(message, self.profile_id),
                self.integrity_key_id,
                "",
            )
            return replace(request, request_mac=self._mac(request))
        except (ValueError, TypeError, UnicodeError):
            raise InvalidTelnyxRequest("Invalid offline Telnyx request") from None

    def _mac(self, request: TelnyxRequest) -> str:
        return hmac.new(self.integrity_key, request.integrity_input(), hashlib.sha256).hexdigest()

    def verify(self, request: TelnyxRequest) -> bool:
        return (
            request.canonical_for(request.message)
            and request.organization_id == self.organization_id
            and request.profile_id == self.profile_id
            and request.integrity_key_id == self.integrity_key_id
            and hmac.compare_digest(request.request_mac, self._mac(request))
        )


def bind_http_request(
    connection: sqlite3.Connection,
    request: TelnyxRequest,
    message: OutboundMessage,
) -> bool:
    """Caller owns authorization's writer transaction; no independent commit or I/O."""
    if not request.canonical_for(message):
        return False
    if not connection.execute(
        "SELECT 1 FROM eligible_telnyx_channels AS eligible JOIN channel_lifecycle AS channel "
        "ON channel.channel_id=eligible.channel_id WHERE channel.channel_id=? "
        "AND channel.organization_id=? AND channel.profile_id=?",
        (message.sender_address, request.organization_id, request.profile_id),
    ).fetchone():
        return False
    identity = (request.version, request.integrity_key_id, request.request_mac)
    existing = connection.execute(
        "SELECT version,integrity_key_id,request_mac FROM telnyx_http_requests "
        "WHERE submission_key=?",
        (message.submission_key,),
    ).fetchone()
    if existing is not None:
        return hmac.compare_digest("|".join(existing), "|".join(identity))
    connection.execute(
        "INSERT INTO telnyx_http_requests(submission_key,version,integrity_key_id,request_mac) "
        "VALUES(?,?,?,?)",
        (message.submission_key, *identity),
    )
    return True
