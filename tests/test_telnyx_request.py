"""Exact synthetic request; no network implementation exists in this component."""

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest
from telnyx_channel_fixture import verified_channel
from test_telnyx_authentication import ORG, PHONE, PROFILE

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.persistence import SqliteConversationStore
from rj_studio_ai.telnyx_request import InvalidTelnyxRequest, TelnyxRequestSigner, bind_http_request


@pytest.fixture
def signer():
    return TelnyxRequestSigner(ORG, PROFILE, "synthetic-v1", b"synthetic-integrity-only-00000000")


@pytest.fixture
def message():
    return OutboundMessage(PHONE, "+5511999999999", 'Olá\n"texto" ☀', submission_key=str(uuid4()))


def test_serialization_exact_bytes_restart_and_key(signer, message):
    request = signer.prepare(message)
    assert (
        request.content
        == json.dumps(
            {
                "from": PHONE,
                "to": message.recipient_address,
                "type": "WHATSAPP",
                "messaging_profile_id": PROFILE,
                "whatsapp_message": {
                    "type": "text",
                    "text": {"body": message.body, "preview_url": False},
                },
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    )
    assert dict(request.headers)["Idempotency-Key"] == message.submission_key
    assert signer.prepare(message) == request
    restarted = replace(signer)
    assert restarted.prepare(message) == request
    assert request.canonical_for(message) and signer.verify(request)
    for private in (message.body, PHONE, PROFILE, ORG, message.submission_key):
        assert private not in repr(request) + repr(signer)


@pytest.mark.parametrize(
    "change",
    [
        {"method": "GET"},
        {"host": "attacker.invalid"},
        {"scheme": "http"},
        {"path": "/v2/messages"},
        {"query": b"a=1"},
        {"content": b"{}"},
        {"content_type": "text/plain"},
        {"organization_id": "other"},
        {"profile_id": "other"},
        {"request_mac": "0" * 64},
        {"integrity_key_id": "other"},
        {"version": "t11-v2"},
    ],
)
def test_every_material_change_fails_integrity(signer, message, change):
    assert not signer.verify(replace(signer.prepare(message), **change))


@pytest.mark.parametrize(
    "change",
    [
        {"body": "different"},
        {"recipient_address": "+5511888888888"},
        {"sender_address": "+5511777777777"},
        {"submission_key": str(uuid4())},
    ],
)
def test_payload_or_key_change_changes_mac(signer, message, change):
    first = signer.prepare(message)
    second = signer.prepare(replace(message, **change))
    assert first.request_mac != second.request_mac
    assert not first.canonical_for(second.message)


@pytest.mark.parametrize(
    "change",
    [
        {"submission_key": None},
        {"submission_key": "bad"},
        {"recipient_address": "bsuid:US.13491208655302741918"},
        {"body": ""},
        {"sender_address": "https://attacker.invalid"},
    ],
)
def test_invalid_request_fails_locally_without_values(signer, message, change):
    with pytest.raises(InvalidTelnyxRequest, match="^Invalid offline Telnyx request$"):
        signer.prepare(replace(message, **change))


def test_durable_binding_scope_rotation_and_rollback(tmp_path, signer, message):
    store = SqliteConversationStore(tmp_path / "synthetic.db")
    store.initialize()
    verified_channel(tmp_path / "synthetic.db")
    request = signer.prepare(message)
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        assert not bind_http_request(db, replace(request, organization_id="other"), message)
        assert not bind_http_request(db, replace(request, host="attacker.invalid"), message)
        assert bind_http_request(db, request, message)
        assert bind_http_request(db, request, message)
        assert not bind_http_request(
            db, replace(signer, integrity_key=b"x" * 32).prepare(message), message
        )
        db.rollback()
        assert db.execute("SELECT * FROM telnyx_http_requests").fetchall() == []
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        assert bind_http_request(db, request, message)
    restarted = SqliteConversationStore(tmp_path / "synthetic.db")
    with restarted._connect() as db:
        assert bind_http_request(db, request, message)
        for sql in (
            "DELETE FROM telnyx_http_requests",
            "UPDATE telnyx_http_requests SET request_mac='x'",
            "INSERT OR REPLACE INTO telnyx_http_requests SELECT * FROM telnyx_http_requests",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(sql)
        row = db.execute("SELECT * FROM telnyx_http_requests").fetchone()
        assert row == (message.submission_key, "t11-v1", "synthetic-v1", request.request_mac)
    assert restarted.migrations_are_current()


@pytest.mark.parametrize(
    "profile", ["synthetic-profile", "not-a-uuid", "4001781E-626F-4A41-A914-B1B682150F94"]
)
def test_profile_requires_official_canonical_uuid(signer, profile):
    with pytest.raises(
        InvalidTelnyxRequest, match="^Invalid offline Telnyx integrity configuration$"
    ):
        replace(signer, profile_id=profile)
