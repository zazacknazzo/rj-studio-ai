"""Raw ASGI messages retain duplicates/fragmentation unavailable in header dicts."""

import asyncio

import pytest

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.telnyx_http import TelnyxHTTPError, read_telnyx_request


def read(headers=(), chunks=(b"{}",), *, max_bytes=16, messages=None):
    async def run():
        pending = (
            list(messages)
            if messages is not None
            else [
                {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
                for i, chunk in enumerate(chunks)
            ]
        )

        async def receive():
            return pending.pop(0)

        return await read_telnyx_request(
            {"method": "POST", "headers": [(b"content-type", b"application/json"), *headers]},
            receive,
            max_bytes=max_bytes,
            deadline=ExecutionDeadline.start(),
        )

    return asyncio.run(run())


@pytest.mark.parametrize(
    "header", [b"telnyx-timestamp", b"telnyx-signature-ed25519", b"content-length", b"content-type"]
)
def test_raw_duplicate_headers_rejected_before_body(header):
    with pytest.raises(TelnyxHTTPError) as error:
        read([(header, b"1"), (header.upper(), b"1")], messages=[])
    assert error.value.status == 400


@pytest.mark.parametrize("length", [None, b"1", b"99"])
def test_stream_limit_uses_actual_bytes_even_without_honest_length(length):
    with pytest.raises(TelnyxHTTPError) as error:
        read([] if length is None else [(b"content-length", length)], [b"x" * 8] * 3)
    assert error.value.status == 413


@pytest.mark.parametrize("length", [b"1", b"3", b"-1", b"2,2", b"x", b" 2", b""])
def test_malformed_or_inconsistent_lengths(length):
    with pytest.raises(TelnyxHTTPError) as error:
        read([(b"content-length", length)])
    assert error.value.status == 400


def test_fragments_preserve_original_bytes():
    body = b'{ "text": "\xc3\xa1" }'
    result = read([(b"content-length", str(len(body)).encode())], [body[:12], body[12:]])
    assert result.body == body
    assert read([(b"transfer-encoding", b"chunked")]).body == b"{}"


def test_smuggling_ambiguity_disconnect_and_header_budget():
    for headers, messages, status in [
        ([(b"content-length", b"2"), (b"transfer-encoding", b"chunked")], None, 400),
        ([], [{"type": "http.disconnect"}], 400),
        ([(b"other", b"x" * 17000)], None, 431),
        ([(b"other", b"x")] * 101, None, 431),
    ]:
        with pytest.raises(TelnyxHTTPError) as error:
            read(headers, messages=messages)
        assert error.value.status == status


def test_slow_fragment_is_bounded():
    async def run():
        async def receive():
            await asyncio.sleep(1)

        with pytest.raises(TelnyxHTTPError) as error:
            await read_telnyx_request(
                {"method": "POST", "headers": [(b"content-type", b"application/json")]},
                receive,
                max_bytes=16,
                deadline=ExecutionDeadline.start(),
                body_seconds=0.01,
            )
        assert error.value.status == 408

    asyncio.run(run())
