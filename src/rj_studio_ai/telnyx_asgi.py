"""Explicit offline ASGI composition. Never mounted by production main/config."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Lock
from time import monotonic, time

import anyio
from starlette.types import Receive, Scope, Send

from rj_studio_ai.config import Settings
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import InvalidWebhookPayload, InvalidWebhookSignature
from rj_studio_ai.providers.telnyx_messages import TelnyxMessageAdapter
from rj_studio_ai.telnyx_http import TelnyxHTTPError, read_telnyx_request
from rj_studio_ai.webhook_ingress import receive_telnyx_messages


class TelnyxIngressMetrics:
    """Bounded aggregate labels only; never retain individual events/latencies."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._statuses = dict.fromkeys((204, 400, 403, 404, 405, 408, 413, 415, 422, 431, 503), 0)
        self._bounds = (0.01, 0.05, 0.1, 0.5, 1.0, 1.35, 1.5, float("inf"))
        self._buckets = [0] * len(self._bounds)

    def record(self, status: int, seconds: float) -> None:
        with self._lock:
            self._statuses[status] += 1
            for i, bound in enumerate(self._bounds):
                if seconds <= bound:
                    self._buckets[i] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "responses": dict(self._statuses),
                "duration_buckets": {
                    str(bound): count
                    for bound, count in zip(self._bounds, self._buckets, strict=True)
                },
            }


class OfflineTelnyxASGI:
    """Ingress only. Quarantine is structural, outside any restored database.

    No sender, generation worker, outbound worker or release capability exists here.
    Do not mount this synthetic composition on a commercial server.
    """

    TOTAL_SECONDS = 1.5
    WORK_SECONDS = 1.35

    def __init__(
        self,
        settings: Settings,
        store: SqliteConversationStore,
        *,
        wall_clock: Callable[[], float],
        clock: Callable[[], float],
    ) -> None:
        if store._telnyx_egress_quarantined is not True:
            raise ValueError("Offline Telnyx composition requires quarantine")
        self.adapter = TelnyxMessageAdapter(settings, clock=wall_clock)
        self.store = store
        self._max_bytes = settings.telnyx_webhook_max_body_bytes
        self._clock = clock
        self._wall_clock = wall_clock
        self.metrics = TelnyxIngressMetrics()
        self._limiter = anyio.CapacityLimiter(8)
        self._workers = anyio.CapacityLimiter(8)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        if scope["path"] == "/health" and scope["method"] == "GET":
            await self._respond(send, 200, {"process": "ok", "mode": "offline"})
            return
        if scope["path"] == "/ready" and scope["method"] == "GET":
            try:
                readiness = await self._run_work(
                    self.readiness,
                    ExecutionDeadline.start(
                        clock=self._clock,
                        total_seconds=self.WORK_SECONDS,
                        finalization_margin_seconds=0,
                    ),
                )
            except PersistenceUnavailable:
                await self._respond(send, 503)
                return
            await self._respond(send, 200 if readiness["persistence"] else 503, readiness)
            return
        if scope["path"] == "/metrics" and scope["method"] == "GET":
            await self._respond(send, 200, self.metrics.snapshot())
            return
        if scope["path"] != "/webhooks/telnyx":
            await self._respond(send, 404)
            return
        started = self._clock()
        ack = ExecutionDeadline.start(
            clock=self._clock, total_seconds=self.TOTAL_SECONDS, finalization_margin_seconds=0
        )
        work = ExecutionDeadline.start(
            clock=self._clock, total_seconds=self.WORK_SECONDS, finalization_margin_seconds=0
        )
        result = 503
        try:
            if scope["method"] != "POST":
                raise TelnyxHTTPError(405)
            request = await read_telnyx_request(
                scope,
                receive,
                max_bytes=self._max_bytes,
                deadline=work,
                clock=self._clock,
            )
            await self._run_work(
                partial(
                    receive_telnyx_messages,
                    (request,),
                    adapter=self.adapter,
                    store=self.store,
                    deadline=work,
                    now=datetime.fromtimestamp(self._wall_clock(), UTC),
                ),
                work,
            )
            if work.is_expired() or ack.is_expired():
                raise PersistenceUnavailable("Webhook deadline expired")
            result = 204
        except TelnyxHTTPError as error:
            result = error.status
        except InvalidWebhookSignature:
            result = 403
        except (InvalidWebhookPayload, ValueError):
            # Only finite counters, not arbitrary payload/error strings. No success
            # receipt is claimed for unsupported or invalid authenticated payloads.
            try:
                await self._run_work(
                    partial(
                        self.store.record_telnyx_ingress_rejection,
                        deadline=work,
                        now=datetime.fromtimestamp(self._wall_clock(), UTC),
                    ),
                    work,
                )
                result = 503 if work.is_expired() else 422
            except PersistenceUnavailable:
                result = 503
        except PersistenceUnavailable:
            result = 503
        # Check at the response boundary as well; never emit success after expiry.
        if result == 204 and ack.is_expired():
            result = 503
        try:
            await self._respond(send, result)
        finally:
            self.metrics.record(result, max(0, self._clock() - started))

    async def _run_work(self, function: Callable, deadline: ExecutionDeadline):
        # Queueing is cancellable/bounded. Once SQL/commit starts, wait for its
        # result and check the deadline; never detach a running transaction.
        try:
            with anyio.fail_after(deadline.remaining_budget()):
                await self._limiter.acquire()
        except TimeoutError:
            raise PersistenceUnavailable("Webhook ingress capacity deadline expired") from None
        try:
            if deadline.is_expired():
                raise PersistenceUnavailable("Webhook ingress deadline expired")
            # Only admitted jobs use these workers, so admission reserves a slot.
            job = asyncio.create_task(anyio.to_thread.run_sync(function, limiter=self._workers))
            try:
                return await asyncio.shield(job)
            except asyncio.CancelledError:
                # ASGI cancellation may use asyncio.Task.cancel(), which bypasses
                # AnyIO's default shield. Drain the admitted job before releasing
                # capacity, even under repeated cancellation. Do not send an ACK.
                while not job.done():
                    try:
                        await asyncio.shield(job)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not job.cancelled():
                    job.exception()  # consume failure; cancellation remains authoritative
                raise
        finally:
            self._limiter.release()

    def readiness(self) -> dict:
        checks = self.store.sqlite_durability_checks()
        persistent = (
            all(value == "ok" for value in checks.values())
            and self.store.migrations_are_current()
            and self.store.is_writable()
        )
        return {
            "mode": "offline",
            "ingress": self.adapter.is_configured(),
            "persistence": persistent,
            "administration": False,
            "generation": False,
            "egress": False,
            "operational_channel": False,
            "quarantined": True,
        }

    @staticmethod
    async def _respond(send: Send, status: int, payload: dict | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def create_telnyx_offline_app(
    settings: Settings,
    database_path: Path,
    *,
    wall_clock: Callable[[], float] = time,
    monotonic_clock: Callable[[], float] = monotonic,
) -> OfflineTelnyxASGI:
    """Explicit synthetic entry point; no module-level app or production selector."""
    store = SqliteConversationStore(
        database_path, busy_timeout_seconds=0.5, telnyx_egress_quarantined=True
    )
    app = OfflineTelnyxASGI(settings, store, wall_clock=wall_clock, clock=monotonic_clock)
    store.initialize()
    return app
