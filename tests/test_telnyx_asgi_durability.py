"""Inject failures at actual transaction/ASGI boundaries, without external transport."""

import asyncio
import sqlite3
from contextlib import contextmanager
from threading import Event
from time import monotonic

import pytest
from starlette.testclient import TestClient
from test_telnyx_asgi import app as app
from test_telnyx_asgi import count, post
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_authentication import signed
from test_telnyx_messages import wire


async def raw_call(app, request, *, chunks=None, on_send=None):
    pending = list(chunks or [request.body])
    sent = []

    async def receive():
        chunk = pending.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(pending)}

    async def send(message):
        if on_send:
            on_send(message)
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": "/webhooks/telnyx",
            "headers": [
                (b"content-type", b"application/json"),
                *[(k.encode(), v.encode()) for k, v in request.headers.items()],
            ],
        },
        receive,
        send,
    )
    return sent[0]["status"]


def test_stream_fragmentation_commit_is_visible_before_response_start(app, private_key):
    request = signed(private_key, wire())

    def inspect(message):
        if message["type"] == "http.response.start":
            assert message["status"] == 204
            with sqlite3.connect(app.store._database_path) as db:
                assert db.execute("SELECT COUNT(*) FROM messages").fetchone() == (1,)
                assert db.execute("SELECT COUNT(*) FROM inbound_event_receipts").fetchone() == (1,)

    assert (
        asyncio.run(
            raw_call(
                app,
                request,
                chunks=[request.body[i : i + 7] for i in range(0, len(request.body), 7)],
                on_send=inspect,
            )
        )
        == 204
    )


def test_lost_ack_at_asgi_send_replays_without_second_admission(app, private_key):
    def lost(message):
        raise ConnectionError("synthetic lost ACK")

    request = signed(private_key, wire())
    with pytest.raises(ConnectionError):
        asyncio.run(raw_call(app, request, on_send=lost))
    assert count(app, "messages") == 1
    assert asyncio.run(raw_call(app, request)) == 204
    assert count(app, "messages") == 1


@pytest.mark.parametrize("phase", ["statement", "commit"])
def test_transaction_failure_never_acknowledges_partial_effects(
    app, private_key, monkeypatch, phase
):
    original = app.store._connect
    if phase == "statement":
        with original() as db:
            db.execute(
                "CREATE TRIGGER synthetic_fail BEFORE INSERT ON inbound_event_receipts "
                "BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
            )
    else:

        @contextmanager
        def fail(*args, **kwargs):
            with original(*args, **kwargs) as db:
                yield db
                raise sqlite3.OperationalError("synthetic fsync failure")

        monkeypatch.setattr(app.store, "_connect", fail)
    with TestClient(app) as client:
        assert post(client, private_key).status_code == 503
    monkeypatch.setattr(app.store, "_connect", original)
    for table in ("messages", "inbound_event_receipts", "channel_lifecycle"):
        assert count(app, table) == 0
    if phase == "statement":
        with original() as db:
            db.execute("DROP TRIGGER synthetic_fail")
    with TestClient(app) as client:
        assert post(client, private_key).status_code == 204


def test_sqlite_writer_lock_has_bounded_wait_and_retry(app, private_key):
    with app.store._connect() as lock:
        lock.execute("BEGIN IMMEDIATE")
        started = monotonic()
        with TestClient(app) as client:
            assert post(client, private_key).status_code == 503
        assert monotonic() - started < 1.5
        lock.rollback()
    assert count(app, "messages") == 0
    with TestClient(app) as client:
        assert post(client, private_key).status_code == 204


@pytest.mark.parametrize("phase", ["before_parse", "before_commit", "after_commit"])
def test_expired_deadline_never_returns_success(app, private_key, monkeypatch, phase):
    ticks = [0.0]
    app._clock = lambda: ticks[0]
    original = app.store._connect
    if phase == "before_parse":
        original_receive = app.adapter.receive

        def receive(request):
            ticks[0] = 2.0
            return original_receive(request)

        monkeypatch.setattr(app.adapter, "receive", receive)
    else:

        @contextmanager
        def expire(*args, **kwargs):
            with original(*args, **kwargs) as db:
                if phase == "before_commit":
                    db.set_trace_callback(
                        lambda statement: (
                            ticks.__setitem__(0, 2.0)
                            if statement.lstrip().startswith("INSERT INTO messages")
                            else None
                        )
                    )
                yield db
            if phase == "after_commit":
                ticks[0] = 2.0

        monkeypatch.setattr(app.store, "_connect", expire)
    with TestClient(app) as client:
        assert post(client, private_key).status_code == 503
    monkeypatch.setattr(app.store, "_connect", original)
    assert count(app, "messages") == (1 if phase == "after_commit" else 0)


def test_large_signed_payload_within_limit_is_durable(app, private_key):
    payload = wire()
    payload["data"]["payload"]["body"]["text"]["body"] = "x" * 200000
    request = signed(private_key, payload)
    assert len(request.body) < 262144
    assert (
        asyncio.run(raw_call(app, request, chunks=[request.body[:100000], request.body[100000:]]))
        == 204
    )
    with app.store._connect() as db:
        assert db.execute("SELECT length(body) FROM messages").fetchone() == (200000,)


def test_metrics_cannot_delay_success_past_deadline(app, private_key, monkeypatch):
    ticks = [0.0]
    app._clock = lambda: ticks[0]
    monkeypatch.setattr(app.metrics, "record", lambda *_: ticks.__setitem__(0, 2.0))
    observed = []

    def inspect(message):
        if message["type"] == "http.response.start":
            observed.append((message["status"], ticks[0]))

    assert asyncio.run(raw_call(app, signed(private_key, wire()), on_send=inspect)) == 204
    assert observed == [(204, 0.0)]


def test_capacity_wait_is_bounded_without_starting_sql(app, private_key):
    async def run():
        borrowers = [object() for _ in range(8)]
        for borrower in borrowers:
            await app._limiter.acquire_on_behalf_of(borrower)
        try:
            started = monotonic()
            result = await asyncio.wait_for(raw_call(app, signed(private_key, wire())), 1.6)
            assert result == 503 and monotonic() - started < 1.5
        finally:
            for borrower in borrowers:
                app._limiter.release_on_behalf_of(borrower)

    asyncio.run(run())
    assert count(app, "messages") == 0


def test_repeated_asgi_cancellation_drains_persistence_and_holds_admission(
    app, private_key, monkeypatch
):
    entered, release = Event(), Event()
    original = app.store.record_webhook_events

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        original(*args, **kwargs)

    monkeypatch.setattr(app.store, "record_webhook_events", blocked)

    async def run():
        task = asyncio.create_task(raw_call(app, signed(private_key, wire())))
        try:
            while not entered.is_set():
                await asyncio.sleep(0.001)
            for _ in range(3):
                task.cancel()
                await asyncio.sleep(0.01)
                assert not task.done()
                assert app._limiter.borrowed_tokens == 1
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert app._limiter.borrowed_tokens == 0

    asyncio.run(run())
    assert count(app, "messages") == 1
    assert asyncio.run(raw_call(app, signed(private_key, wire()))) == 204
    assert count(app, "messages") == 1
