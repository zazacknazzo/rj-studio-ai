"""Raw ASGI boundary for synthetic Telnyx ingress; no runtime registration."""

import asyncio
import re
from collections.abc import Callable
from time import monotonic

from starlette.types import Receive, Scope

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.providers.base import ProviderWebhookRequest


class TelnyxHTTPError(ValueError):
    def __init__(self, status: int) -> None:
        super().__init__("Telnyx HTTP request rejected")
        self.status = status


async def read_telnyx_request(
    scope: Scope,
    receive: Receive,
    *,
    max_bytes: int,
    deadline: ExecutionDeadline,
    clock: Callable[[], float] = monotonic,
    body_seconds: float = 0.5,
) -> ProviderWebhookRequest:
    """Check duplicates before mapping; bound actual bytes, not claimed length."""
    raw_headers = scope.get("headers", [])
    if len(raw_headers) > 100 or sum(len(k) + len(v) for k, v in raw_headers) > 16384:
        raise TelnyxHTTPError(431)
    # ASGI normally lowercases names. Case folding also makes direct ASGI tests safe.
    selected: dict[str, str] = {}
    for name, value in raw_headers:
        key = name.decode("latin-1").lower()
        if key in {
            "telnyx-signature-ed25519",
            "telnyx-timestamp",
            "content-type",
            "content-length",
            "transfer-encoding",
        }:
            if key in selected:
                raise TelnyxHTTPError(400)
            selected[key] = value.decode("latin-1")
    content_type = selected.get("content-type", "")
    if content_type.lower().split(";", 1)[0].strip() != "application/json":
        raise TelnyxHTTPError(415)
    length = selected.get("content-length")
    transfer = selected.get("transfer-encoding")
    if transfer is not None and (length is not None or transfer.lower() != "chunked"):
        raise TelnyxHTTPError(400)
    if length is not None:
        if not re.fullmatch(r"[0-9]{1,10}", length):
            raise TelnyxHTTPError(400)
        if int(length) > max_bytes:
            raise TelnyxHTTPError(413)
    expires = clock() + min(body_seconds, deadline.remaining_budget())
    body = bytearray()
    while True:
        remaining = min(expires - clock(), deadline.remaining_budget())
        if remaining <= 0:
            raise TelnyxHTTPError(408)
        try:
            message = await asyncio.wait_for(receive(), remaining)
        except TimeoutError:
            raise TelnyxHTTPError(408) from None
        if message["type"] != "http.request":
            raise TelnyxHTTPError(400)
        chunk = message.get("body", b"")
        if len(chunk) > max_bytes - len(body):
            raise TelnyxHTTPError(413)
        body.extend(chunk)
        if not message.get("more_body", False):
            break
    if not body or (length is not None and int(length) != len(body)):
        raise TelnyxHTTPError(400)
    return ProviderWebhookRequest(
        method=scope["method"],
        url="https://offline.invalid/webhooks/telnyx",
        headers=selected,
        query_string=scope.get("query_string", b""),
        content_type=content_type,
        body=bytes(body),
    )
