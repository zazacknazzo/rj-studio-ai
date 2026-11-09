import base64
import hashlib
import json
import sqlite3
import traceback
from dataclasses import replace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app
from rj_studio_ai.persistence import SqliteConversationStore
from rj_studio_ai.providers.base import (
    InboundWebhookAdapter,
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    OutboundMessageSender,
    ProviderWebhookRequest,
)
from rj_studio_ai.providers.telnyx import TelnyxConfigurationError, TelnyxWebhookAuthenticator

NOW = 1_800_000_000
PHONE = "+15555550100"
PROFILE = "synthetic-profile"
WABA = "synthetic-waba"
ORG = "synthetic-organization"
PRIVATE_TEXT = "PRIVATE-content-Lívia-✨"
OPERATOR_SECRET = "synthetic-operator-secret-at-least-32-characters"


@pytest.fixture
def private_key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def settings(private_key):
    return Settings(
        _env_file=None,
        delivery_mode="proactive",
        telnyx_public_key=base64.b64encode(private_key.public_key().public_bytes_raw()).decode(),
        telnyx_phone_number=PHONE,
        telnyx_messaging_profile_id=PROFILE,
        telnyx_waba_id=WABA,
        telnyx_organization_id=ORG,
    )


def message(event_type="message.received"):
    inbound = event_type == "message.received"
    return {
        "data": {
            "record_type": "event",
            "id": "synthetic-envelope",
            "event_type": event_type,
            "occurred_at": "2000-01-01T00:00:00Z",
            "payload": {
                "record_type": "message",
                "type": "WHATSAPP",
                "direction": "inbound" if inbound else "outbound",
                "organization_id": ORG,
                "messaging_profile_id": PROFILE,
                "from": {"phone_number": "+15555550101" if inbound else PHONE},
                "to": PHONE if inbound else "+15555550101",
                "body": {"text": {"body": PRIVATE_TEXT}},
            },
        },
    }


def lifecycle():
    return {
        "data": {
            "record_type": "event",
            "event_type": "whatsapp.account.update",
            "payload": {
                "record_type": "whatsapp_account",
                "waba_id": WABA,
                "event": "ACCOUNT_OFFBOARDED",
            },
        },
    }


def signed(private_key, payload=None, *, body=None, timestamp=str(NOW)):
    if body is None:
        body = (
            json.dumps(
                message() if payload is None else payload, ensure_ascii=False, indent=2
            ).encode("utf-8")
            + b"\n"
        )
    signature = private_key.sign(timestamp.encode("utf-8") + b"|" + body)
    return ProviderWebhookRequest(
        method="POST",
        url="https://example.invalid/webhooks/telnyx",
        query_string=b"",
        content_type="application/json; charset=utf-8",
        body=body,
        headers={
            "telnyx-timestamp": timestamp,
            "telnyx-signature-ed25519": base64.b64encode(signature).decode(),
        },
    )


def authenticator(settings, now=NOW):
    return TelnyxWebhookAuthenticator(settings, clock=lambda: now)


@pytest.mark.parametrize(
    "event_type",
    [
        "message.received",
        "message.echo",
        "message.sent",
        "message.finalized",
        "message.read",
    ],
)
def test_valid_ed25519_returns_exact_bytes_without_canonical_parsing(
    settings, private_key, event_type
):
    webhook = signed(private_key, message(event_type))
    result = authenticator(settings).authenticate(webhook)
    assert result is webhook.body
    assert PRIVATE_TEXT.encode("utf-8") in result
    assert b"\n  " in result
    assert not isinstance(result, InboundWebhookAdapter)


@pytest.mark.parametrize(
    "transform",
    [
        lambda body: body + b" ",
        lambda body: json.dumps(json.loads(body)).encode(),
        lambda body: body.replace(b"PRIVATE", b"ALTERED"),
        lambda body: body.replace("í".encode(), "i\u0301".encode()),
    ],
)
def test_altered_body_fails_even_when_json_is_equivalent(settings, private_key, transform):
    webhook = signed(private_key)
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(replace(webhook, body=transform(webhook.body)))


@pytest.mark.parametrize(
    "signature",
    [
        "",
        "not-base64",
        "é" * 88,
        " " * 88,
        base64.b64encode(b"x" * 63).decode(),
        base64.b64encode(b"x" * 65).decode(),
        base64.b64encode(b"x" * 64).decode(),
    ],
)
def test_invalid_signature(settings, private_key, signature):
    webhook = signed(private_key)
    webhook.headers["telnyx-signature-ed25519"] = signature
    with pytest.raises(InvalidWebhookSignature, match="^Invalid Telnyx webhook signature$"):
        authenticator(settings).authenticate(webhook)


@pytest.mark.parametrize("header", ["telnyx-timestamp", "telnyx-signature-ed25519"])
def test_missing_authentication_header(settings, private_key, header):
    webhook = signed(private_key)
    del webhook.headers[header]
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(webhook)


def test_wrong_public_key_and_tampered_timestamp(settings, private_key):
    webhook = signed(Ed25519PrivateKey.generate())
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(webhook)
    webhook = signed(private_key)
    webhook.headers["telnyx-timestamp"] = str(NOW + 1)
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(webhook)


@pytest.mark.parametrize(
    "timestamp",
    [
        "",
        "-1",
        "+1800000000",
        "1800000000.0",
        "1.8e9",
        " 1800000000",
        "1800000000\n",
        "١٨٠٠٠٠٠٠٠٠",
        "9" * 5000,
        str(NOW - 301),
        str(NOW + 301),
    ],
)
def test_invalid_or_stale_timestamp_fails_with_real_signature(settings, private_key, timestamp):
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(signed(private_key, timestamp=timestamp))


@pytest.mark.parametrize("delta", [-300, -299, 0, 299, 300])
def test_signature_window_includes_both_boundaries(settings, private_key, delta):
    webhook = signed(private_key, timestamp=str(NOW + delta))
    assert authenticator(settings).authenticate(webhook) == webhook.body


def test_timestamp_text_is_not_normalized_before_verification(settings, private_key):
    webhook = signed(private_key, timestamp="0" + str(NOW))
    assert authenticator(settings).authenticate(webhook) == webhook.body


@pytest.mark.parametrize("now", [float("nan"), float("inf"), -float("inf")])
def test_invalid_clock_fails_closed(settings, private_key, now):
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings, now).authenticate(signed(private_key))


def test_custom_window_and_fresh_signature_on_old_event(settings, private_key):
    settings.telnyx_webhook_tolerance_seconds = 10
    auth = authenticator(settings)
    webhook = signed(private_key)
    assert auth.authenticate(webhook) == webhook.body  # occurred_at is deliberately old
    assert auth.authenticate(webhook) == webhook.body  # no deduplication in authentication
    with pytest.raises(InvalidWebhookSignature):
        auth.authenticate(signed(private_key, timestamp=str(NOW - 11)))
    with pytest.raises(InvalidWebhookSignature):
        auth.authenticate(signed(private_key, timestamp=str(NOW + 11)))
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings, NOW + 11).authenticate(webhook)
    assert (
        authenticator(settings, NOW + 11).authenticate(signed(private_key, timestamp=str(NOW + 11)))
        == webhook.body
    )


def test_case_insensitive_headers_and_ambiguous_headers(settings, private_key):
    webhook = signed(private_key)
    mixed = replace(webhook, headers={k.title(): v for k, v in webhook.headers.items()})
    assert authenticator(settings).authenticate(mixed) == webhook.body
    for header in webhook.headers:
        duplicate = replace(
            webhook, headers={**webhook.headers, header.title(): webhook.headers[header]}
        )
        with pytest.raises(InvalidWebhookSignature):
            authenticator(settings).authenticate(duplicate)
        joined = replace(
            webhook, headers={**webhook.headers, header: webhook.headers[header] + ",junk"}
        )
        with pytest.raises(InvalidWebhookSignature):
            authenticator(settings).authenticate(joined)


def test_body_limit_counts_bytes_before_parsing(settings, private_key, monkeypatch):
    webhook = signed(private_key)
    settings.telnyx_webhook_max_body_bytes = len(webhook.body)
    assert authenticator(settings).authenticate(webhook) == webhook.body
    settings.telnyx_webhook_max_body_bytes -= 1
    parser = Mock(side_effect=AssertionError("must not parse oversized body"))
    monkeypatch.setattr("rj_studio_ai.providers.telnyx.json.loads", parser)
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(webhook)
    parser.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        b"{broken",
        b"\xff",
        b"[]",
        b"null",
        b'{"data": []}',
        b'{"data": {"payload": []}}',
        b'{"data": {}, "data": {}}',
        b'{"data": NaN}',
        b'{"data": Infinity}',
        b"[" * 1100 + b"]" * 1100,
    ],
)
def test_signed_malformed_json_has_safe_error(settings, private_key, body):
    with pytest.raises(InvalidWebhookPayload) as error:
        authenticator(settings).authenticate(signed(private_key, body=body))
    assert error.value.__suppress_context__ or error.value.__context__ is None


def test_authentication_precedes_any_json_inspection(settings, private_key, monkeypatch):
    webhook = signed(private_key, body=b'{"sensitive": "PRIVATE"')
    webhook.headers["telnyx-signature-ed25519"] = ""
    parser = Mock(side_effect=AssertionError("must not parse unauthenticated body"))
    monkeypatch.setattr("rj_studio_ai.providers.telnyx.json.loads", parser)
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(webhook)
    parser.assert_not_called()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("telnyx_public_key", ""),
        ("telnyx_public_key", "malformed-key"),
        ("telnyx_public_key", base64.b64encode(b"x" * 31).decode()),
        ("telnyx_public_key", base64.b64encode(b"x" * 33).decode()),
        ("telnyx_public_key", "é" * 44),
        ("telnyx_public_key", " " * 44),
        ("telnyx_phone_number", ""),
        ("telnyx_phone_number", "+01234"),
        ("telnyx_phone_number", "15555550100"),
        ("telnyx_phone_number", "+15555550100\n"),
        ("telnyx_messaging_profile_id", ""),
        ("telnyx_messaging_profile_id", " space "),
        ("telnyx_waba_id", ""),
        ("telnyx_organization_id", ""),
        ("delivery_mode", "legacy"),
        ("telnyx_webhook_max_body_bytes", 0),
        ("telnyx_webhook_max_body_bytes", 1_048_577),
        ("telnyx_webhook_max_body_bytes", True),
        ("telnyx_webhook_tolerance_seconds", 0),
        ("telnyx_webhook_tolerance_seconds", 301),
        ("telnyx_webhook_tolerance_seconds", float("nan")),
    ],
)
def test_incomplete_invalid_or_mutated_configuration_fails_closed(settings, field, value):
    setattr(settings, field, value)
    with pytest.raises(TelnyxConfigurationError, match="^Invalid Telnyx ingress configuration$"):
        authenticator(settings)


@pytest.mark.parametrize(
    "field", ["telnyx_webhook_max_body_bytes", "telnyx_webhook_tolerance_seconds"]
)
def test_invalid_environment_limits_are_redacted(field, monkeypatch):
    monkeypatch.setenv(field.upper(), PRIVATE_TEXT)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert PRIVATE_TEXT not in str(error.value)
    assert PRIVATE_TEXT not in error.value.json()
    assert PRIVATE_TEXT not in str(error.value.errors())


def test_configuration_snapshot_has_no_send_or_admin_authority(settings, private_key):
    auth = authenticator(settings)
    assert not isinstance(auth, InboundWebhookAdapter)
    assert not isinstance(auth, OutboundMessageSender)
    assert not hasattr(auth, "send")
    assert not hasattr(auth, "acknowledge")
    assert not hasattr(auth, "is_configured")
    settings.telnyx_public_key = ""
    settings.telnyx_phone_number = ""
    assert auth.authenticate(signed(private_key))
    with pytest.raises(TelnyxConfigurationError):
        authenticator(settings)


@pytest.mark.parametrize("field", ["messaging_profile_id", "organization_id", "to"])
@pytest.mark.parametrize("missing", [False, True])
def test_signed_message_rejects_wrong_or_missing_scope(settings, private_key, field, missing):
    payload = message()
    if missing:
        del payload["data"]["payload"][field]
    else:
        payload["data"]["payload"][field] = "wrong-scope"
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(signed(private_key, payload))


@pytest.mark.parametrize(
    "event_type", ["message.echo", "message.sent", "message.finalized", "message.read"]
)
def test_outbound_scope_uses_business_sender_not_recipient(settings, private_key, event_type):
    payload = message(event_type)
    payload["data"]["payload"]["from"]["phone_number"] = "wrong-channel"
    payload["data"]["payload"]["to"] = PHONE
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(signed(private_key, payload))


@pytest.mark.parametrize(
    "field,value",
    [
        ("type", "SMS"),
        ("direction", "outbound"),
        ("record_type", "wrong"),
        ("waba_id", "wrong-waba"),
        ("waba_id", None),
    ],
)
def test_contradictory_message_scope_fails(settings, private_key, field, value):
    payload = message()
    payload["data"]["payload"][field] = value
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(signed(private_key, payload))


def test_lifecycle_scoped_to_waba_without_message_fields(settings, private_key):
    webhook = signed(private_key, lifecycle())
    assert authenticator(settings).authenticate(webhook) == webhook.body
    for value in ["wrong-waba", None, "", 123]:
        payload = lifecycle()
        payload["data"]["payload"]["waba_id"] = value
        with pytest.raises(InvalidWebhookPayload):
            authenticator(settings).authenticate(signed(private_key, payload))
    payload = lifecycle()
    del payload["data"]["payload"]["waba_id"]
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(signed(private_key, payload))


@pytest.mark.parametrize("event_type", ["whatsapp.messages", "unknown", None, {}, []])
def test_unknown_contract_has_no_scope_authority(settings, private_key, event_type):
    payload = message()
    payload["data"]["event_type"] = event_type
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(signed(private_key, payload))


@pytest.mark.parametrize(
    "change",
    [dict(method="GET"), dict(content_type="text/plain"), dict(body=b""), dict(body="not-bytes")],
)
def test_invalid_request_shape(settings, private_key, change):
    with pytest.raises(InvalidWebhookPayload):
        authenticator(settings).authenticate(replace(signed(private_key), **change))


def test_bearer_never_substitutes_for_ed25519(settings, private_key):
    settings.operator_secret_sha256 = hashlib.sha256(OPERATOR_SECRET.encode()).hexdigest()
    webhook = replace(signed(private_key), headers={"Authorization": f"Bearer {OPERATOR_SECRET}"})
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(webhook)


@pytest.mark.parametrize("mode", ["legacy", "proactive"])
def test_telnyx_cannot_be_selected_in_runtime(settings, mode):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, whatsapp_provider="telnyx", delivery_mode=mode)


def test_http_has_no_telnyx_route_or_operational_effects(settings, private_key, tmp_path):
    settings.database_path = tmp_path / "isolated.db"
    store = SqliteConversationStore(settings.database_path)
    store.initialize()
    client = TestClient(create_app(settings, store=store))
    with sqlite3.connect(settings.database_path) as connection:
        before = tuple(connection.iterdump())
    webhook = signed(private_key)
    for headers in [{}, webhook.headers, {"Authorization": f"Bearer {OPERATOR_SECRET}"}]:
        response = client.post("/webhooks/telnyx", content=webhook.body, headers=headers)
        assert response.status_code == 404
    assert client.get("/ready").status_code == 503  # ingress config is not send readiness
    for payload in [message(), message("message.echo"), lifecycle()]:
        signed_request = signed(private_key, payload)
        assert authenticator(settings).authenticate(signed_request) == signed_request.body
        with pytest.raises(InvalidWebhookSignature):
            authenticator(settings).authenticate(replace(signed_request, headers={}))
    with sqlite3.connect(settings.database_path) as connection:
        assert tuple(connection.iterdump()) == before


def test_settings_errors_and_logs_never_expose_private_values(settings, private_key, caplog):
    webhook = signed(private_key)
    signature = webhook.headers["telnyx-signature-ed25519"]
    public_key = settings.telnyx_public_key
    values = [PHONE, PROFILE, WABA, ORG, PRIVATE_TEXT, signature, public_key, OPERATOR_SECRET]
    surfaces = [
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        str(settings.model_dump()),
        repr(authenticator(settings)),
    ]
    for request in [
        replace(webhook, body=webhook.body + b" "),
        signed(private_key, body=b'{"PRIVATE-content-Livia":'),
        replace(webhook, headers={"Authorization": f"Bearer {OPERATOR_SECRET}"}),
    ]:
        with pytest.raises((InvalidWebhookSignature, InvalidWebhookPayload)) as error:
            authenticator(settings).authenticate(request)
        surfaces.extend(
            [str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))]
        )
    for field in [
        "telnyx_public_key",
        "telnyx_phone_number",
        "telnyx_messaging_profile_id",
        "telnyx_waba_id",
        "telnyx_organization_id",
    ]:
        invalid = settings.model_copy(update={field: PRIVATE_TEXT})
        with pytest.raises(TelnyxConfigurationError) as error:
            authenticator(invalid)
        surfaces.extend([str(error.value), "".join(traceback.format_exception(error.value))])
    surfaces.append(caplog.text)
    for value in values:
        assert all(value not in surface for surface in surfaces)
    assert not caplog.records


@pytest.mark.parametrize(
    "raw_key",
    [
        bytes(32),
        b"\x01" + bytes(31),
        b"\xff" * 32,
        (2**255 - 19).to_bytes(32, "little"),
        b"\x02" + bytes(31),
    ],
)
def test_invalid_curve_keys_reject_forgery_before_authentication(settings, raw_key, private_key):
    # Identity/zero points can accept forgeries with length-only Ed25519 key import.
    # All keys here are deliberately invalid, not private or production material.
    settings.telnyx_public_key = base64.b64encode(raw_key).decode()
    forged = signed(private_key, lifecycle())
    forged.headers["telnyx-signature-ed25519"] = base64.b64encode(b"\x01" + bytes(63)).decode()
    with pytest.raises(TelnyxConfigurationError):
        authenticator(settings).authenticate(forged)


def test_unavailable_point_validation_fails_closed(settings, monkeypatch):
    from nacl.exceptions import UnavailableError

    monkeypatch.setattr(
        "rj_studio_ai.providers.telnyx.crypto_core_ed25519_is_valid_point",
        Mock(side_effect=UnavailableError("synthetic-private-input")),
    )
    with pytest.raises(TelnyxConfigurationError) as error:
        authenticator(settings)
    assert "synthetic-private-input" not in "".join(traceback.format_exception(error.value))


def test_signature_over_body_without_timestamp_prefix_is_rejected(settings, private_key):
    webhook = signed(private_key)
    webhook.headers["telnyx-signature-ed25519"] = base64.b64encode(
        private_key.sign(webhook.body)
    ).decode()
    with pytest.raises(InvalidWebhookSignature):
        authenticator(settings).authenticate(webhook)
