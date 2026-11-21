"""Controlled in-process ASGI load; percentiles describe this host, not Telnyx."""

import asyncio
import json
import math
from collections import Counter
from time import monotonic

import pytest
from test_telnyx_asgi import app as app
from test_telnyx_asgi import count
from test_telnyx_asgi_durability import raw_call
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_authentication import signed
from test_telnyx_messages import wire


@pytest.mark.parametrize("duplicate", [False, True])
def test_controlled_load_reports_offline_percentiles(app, private_key, record_property, duplicate):
    requests = [
        signed(
            private_key,
            wire(
                event_id=f"load-{0 if duplicate else i}",
                message_id=f"load-message-{0 if duplicate else i}",
            ),
        )
        for i in range(128)
    ]

    async def run():
        semaphore = asyncio.Semaphore(8)
        samples = []

        async def one(request):
            async with semaphore:
                started = monotonic()
                status = await raw_call(app, request, chunks=[request.body[:71], request.body[71:]])
                samples.append((monotonic() - started, status, request))

        await asyncio.gather(*(one(request) for request in requests))
        return samples

    samples = asyncio.run(run())
    durations = sorted(duration for duration, _, _ in samples)
    results = {
        "mode": "synthetic_asgi_sqlite_wal_full",
        "requests": len(samples),
        "concurrency": 8,
        "duplicate": duplicate,
        "p95_seconds": durations[math.ceil(len(samples) * 0.95) - 1],
        "p99_seconds": durations[math.ceil(len(samples) * 0.99) - 1],
        "max_seconds": max(durations),
        "responses": dict(Counter(status for _, status, _ in samples)),
        "late_successes": sum(duration >= 1.5 and status == 204 for duration, status, _ in samples),
    }

    # Contention may produce explicit backpressure. Retry identical envelopes
    # after load drains; every durable event must then exist exactly once.
    async def retry():
        return [await raw_call(app, request) for _, status, request in samples if status == 503]

    retries = asyncio.run(retry())
    results["retry_responses"] = dict(Counter(retries))
    record_property("ticket12_offline_load", json.dumps(results, sort_keys=True))
    assert results["late_successes"] == 0
    assert set(results["responses"]) <= {204, 503}
    assert all(status == 204 for status in retries)
    assert count(app, "messages") == (1 if duplicate else 128)
    assert count(app, "inbound_event_receipts") == (1 if duplicate else 128)
    assert count(app, "outbound_deliveries") == 0
