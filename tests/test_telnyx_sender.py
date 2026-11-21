"""Intercepted responses exercise the concrete adapter without any HTTP client."""

import json
import traceback
from dataclasses import replace

import pytest
from test_telnyx_request import message as message
from test_telnyx_request import signer as signer

from rj_studio_ai.providers.telnyx_sender import (
    TelnyxHttpResponse,
    TelnyxOutcomeUnknown,
    TelnyxWhatsAppSender,
)
from rj_studio_ai.telnyx_request import InvalidTelnyxRequest

MESSAGE_ID = "synthetic-telnyx-acceptance"


def acceptance(request, *, status="queued"):
    return {
        "data": {
            "record_type": "message",
            "direction": "outbound",
            "id": MESSAGE_ID,
            "type": "WHATSAPP",
            "organization_id": request.organization_id,
            "messaging_profile_id": request.profile_id,
            "from": {"phone_number": request.message.sender_address},
            "to": [{"phone_number": request.message.recipient_address, "status": status}],
            "body": {"type": "text", "text": {"body": request.message.body, "preview_url": False}},
        }
    }


def response(payload, status=200):
    return TelnyxHttpResponse(status, json.dumps(payload).encode())


@pytest.mark.parametrize("status", ["queued", "sending", "sent", "delivered", "read"])
def test_strict_acceptance_and_transport_policy(signer, message, status):
    calls = []

    def exchange(request, **policy):
        calls.append((request, policy))
        return response(acceptance(request, status=status))

    sender = TelnyxWhatsAppSender(signer, exchange)
    prepared = sender.prepare(message)
    result = sender.send_prepared(prepared, timeout_seconds=9)
    assert result.provider_message_id == MESSAGE_ID
    assert calls == [
        (
            prepared,
            {
                "connect_timeout_seconds": 3,
                "read_timeout_seconds": 6,
                "retries": 0,
                "follow_redirects": False,
            },
        )
    ]


@pytest.mark.parametrize(
    "path,value",
    [
        (("data", "id"), None),
        (("data", "id"), ""),
        (("data", "id"), "secret\n"),
        (("data", "type"), "SMS"),
        (("data", "organization_id"), "other"),
        (("data", "messaging_profile_id"), "other"),
        (("data", "direction"), "inbound"),
        (("data", "record_type"), "event"),
        (("data", "from", "phone_number"), "+5511888888888"),
        (("data", "to", 0, "phone_number"), "+5511888888888"),
        (("data", "to", 0, "status"), "future_status"),
        (("data", "to", 0, "status"), "failed"),
        (("data", "to"), []),
        (("data", "body", "text", "body"), "changed"),
        (("data", "body", "text", "preview_url"), True),
        (("data", "origin"), "whatsapp_business_app"),
        (("data", "errors"), [{"code": "secret"}]),
        (("data", "body"), None),
    ],
)
def test_incomplete_or_mismatched_acceptance_unknown(signer, message, path, value):
    def exchange(request, **_):
        payload = acceptance(request)
        parent = payload
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = value
        return response(payload)

    sender = TelnyxWhatsAppSender(signer, exchange)
    with pytest.raises(TelnyxOutcomeUnknown, match="^telnyx_response_invalid$"):
        sender.send_prepared(sender.prepare(message), timeout_seconds=9)


@pytest.mark.parametrize(
    "status,code,reason",
    [
        (409, "10036", "telnyx_in_progress"),
        (422, "10027", "telnyx_key_conflict"),
        (409, "10027", "telnyx_http_unknown"),
        (422, "10036", "telnyx_http_unknown"),
        (409, "other", "telnyx_http_unknown"),
        (422, "other", "telnyx_http_unknown"),
        (429, "10036", "telnyx_http_unknown"),
        (500, "10027", "telnyx_http_unknown"),
        (503, "10036", "telnyx_http_unknown"),
        (302, "other", "telnyx_http_unknown"),
        (408, "other", "telnyx_http_unknown"),
        (413, "other", "telnyx_http_unknown"),
    ],
)
def test_specific_error_pairs_never_retry(signer, message, status, code, reason):
    calls = []

    def exchange(request, **_):
        calls.append(request)
        return response({"errors": [{"code": code, "detail": "PRIVATE EXTERNAL DETAIL"}]}, status)

    sender = TelnyxWhatsAppSender(signer, exchange)
    with pytest.raises(TelnyxOutcomeUnknown, match=f"^{reason}$") as error:
        sender.send_prepared(sender.prepare(message), timeout_seconds=9)
    assert error.value.safe_error_code == reason
    assert len(calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"invalid",
        b"{}",
        b"[]",
        b'{"data":{},"data":{}}',
        b'{"data":NaN}',
        b"\xff",
        b"[" * 2000,
        b"x" * 1_048_577,
    ],
)
def test_malformed_success_unknown(signer, message, content):
    sender = TelnyxWhatsAppSender(signer, lambda *_, **__: TelnyxHttpResponse(200, content))
    with pytest.raises(TelnyxOutcomeUnknown, match="^telnyx_response_invalid$"):
        sender.send_prepared(sender.prepare(message), timeout_seconds=9)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("connect PRIVATE"),
        TimeoutError("read PRIVATE"),
        ConnectionResetError("PRIVATE"),
        RuntimeError("lost response PRIVATE"),
    ],
)
def test_every_transport_exception_is_unknown_and_redacted(signer, message, error, caplog):
    calls = []

    def exchange(request, **_):
        calls.append(request)
        raise error

    sender = TelnyxWhatsAppSender(signer, exchange)
    with pytest.raises(TelnyxOutcomeUnknown) as raised:
        sender.send_prepared(sender.prepare(message), timeout_seconds=9)
    assert len(calls) == 1
    assert "PRIVATE" not in "".join(traceback.format_exception(raised.value)) + caplog.text


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_local_validation_never_invokes_transport(signer, message, timeout):
    def unexpected(*_, **__):
        pytest.fail("transport called")

    sender = TelnyxWhatsAppSender(signer, unexpected)
    with pytest.raises(InvalidTelnyxRequest):
        sender.send_prepared(sender.prepare(message), timeout_seconds=timeout)
    with pytest.raises(InvalidTelnyxRequest):
        sender.send(message, timeout_seconds=9)
    with pytest.raises(InvalidTelnyxRequest):
        sender.send_prepared(
            replace(sender.prepare(message), host="attacker.invalid"), timeout_seconds=9
        )


def test_missing_id_wrong_media_and_undocumented_2xx(signer, message):
    request = signer.prepare(message)
    payload = acceptance(request)
    del payload["data"]["id"]
    for value in [
        response(payload),
        TelnyxHttpResponse(200, b"{}", "text/html"),
        response(acceptance(request), 201),
        response({}, 204),
    ]:
        sender = TelnyxWhatsAppSender(signer, lambda *_, result=value, **__: result)
        with pytest.raises(TelnyxOutcomeUnknown):
            sender.send_prepared(request, timeout_seconds=9)
