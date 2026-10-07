"""Explicit outbound-only smoke. No normal app, polling executor or LLM is started."""

import argparse
import json
import logging
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import uuid4

import requests
import uvicorn
from dotenv import dotenv_values
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client

from rj_studio_ai.config import Settings
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.domain import DeliveryStatusReceived, InboundMessage
from rj_studio_ai.live_messaging_smoke import LiveSmokeBlocked, LiveSmokeOutboundSender
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable, SqliteConversationStore
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    ProviderWebhookRequest,
)
from rj_studio_ai.providers.twilio import TwilioOutboundSender, TwilioProvider

_E164 = re.compile(r"\+[1-9][0-9]{6,14}")


class TwilioLiveSmoke:
    def __init__(
        self,
        settings: Settings,
        environment: Mapping[str, str],
        *,
        project_root: Path,
        client_factory=None,
    ):
        self._settings = settings.model_copy(deep=True)
        self._root = project_root.resolve()
        self._controls = {
            key: environment.get(key, "")
            for key in (
                "TWILIO_AUTH_TOKEN_TRUST",
                "TWILIO_SMOKE_SENDER",
                "TEST_WHATSAPP_RECIPIENT",
                "TWILIO_SMOKE_DATABASE_PATH",
                "ALLOW_LIVE_MESSAGING_SMOKE",
            )
        }
        self._sender = TwilioOutboundSender(
            account_sid=self._settings.twilio_account_sid,
            api_key_sid=self._settings.twilio_api_key_sid,
            api_key_secret=self._settings.twilio_api_key_secret,
            status_callback_url=self._settings.twilio_status_callback_url or "",
            client_factory=client_factory or self._client,
        )
        self.smoke_id = uuid4().hex
        self._lock = Lock()
        self._prepared = False
        self._submitted = False
        self._callback_ready = False
        self._callback_failure = Event()
        self._callback_events = set()
        self._callback_duplicates = 0
        self._ignored_callbacks = 0
        self._inbound_id = None

    def _client(self, timeout):
        # The SDK's normal logger emits HTTP URLs/response headers. Smoke logs only metadata.
        quiet = logging.Logger("smoke-wire", level=logging.CRITICAL + 1)
        return Client(
            self._settings.twilio_api_key_sid,
            self._settings.twilio_api_key_secret,
            account_sid=self._settings.twilio_account_sid,
            http_client=TwilioHttpClient(timeout=timeout, max_retries=0, logger=quiet),
        )

    def _database_path(self):
        value = self._controls["TWILIO_SMOKE_DATABASE_PATH"]
        if not value:
            return None
        raw = Path(value)
        return raw if raw.is_absolute() else self._root / raw

    def _isolated_database(self):
        path = self._database_path()
        if path is None or ".." in path.parts or path.name != "smoke-live-messaging.db":
            return False
        allowed = self._root / "work" / "twilio-live-smoke"
        if not path.resolve().is_relative_to(allowed) or path.resolve() == allowed:
            return False
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            return False
        normal = self._settings.database_path
        normal = normal if normal.is_absolute() else self._root / normal
        return path.resolve() != normal.resolve() and not path.exists()

    def _callback_urls(self):
        try:
            inbound = urlsplit(self._settings.twilio_public_webhook_url or "")
            callback = urlsplit(self._settings.twilio_status_callback_url or "")
            _ = inbound.port, callback.port
        except ValueError:
            return False
        return bool(
            all(
                url.scheme == "https"
                and url.hostname
                and not url.username
                and not url.password
                and not url.query
                and not url.fragment
                for url in (inbound, callback)
            )
            and inbound.netloc == callback.netloc
            and inbound.path == "/webhooks/twilio"
            and callback.path == "/webhooks/twilio/status"
        )

    def preflight(self):
        sender = self._controls["TWILIO_SMOKE_SENDER"]
        recipient = self._controls["TEST_WHATSAPP_RECIPIENT"]
        try:
            adapter_config = self._sender.is_configured()
        except ValueError:
            adapter_config = False
        checks = {
            "adapter_config": adapter_config,
            "signature_validation": self._settings.twilio_validate_signature,
            "auth_token_format": bool(
                re.fullmatch(r"[0-9a-fA-F]{32}", self._settings.twilio_auth_token)
            ),
            "token_trust": self._controls["TWILIO_AUTH_TOKEN_TRUST"] == "rotated",
            "sender": bool(_E164.fullmatch(sender)),
            "recipient": bool(_E164.fullmatch(recipient)),
            "recipient_is_not_sender": bool(sender and recipient and sender != recipient),
            "callback_urls": self._callback_urls(),
            "isolated_fresh_database": self._isolated_database(),
            "frozen_candidate": self._settings.llm_provider == "openai"
            and self._settings.openai_model == "gpt-6.1-sol"
            and self._settings.openai_reasoning_effort == "low"
            and self._settings.openai_max_output_tokens == 1024
            and self._settings.whatsapp_provider == "twilio"
            and self._settings.delivery_mode == "proactive",
            "opt_in": self._controls["ALLOW_LIVE_MESSAGING_SMOKE"] == "1",
        }
        if not checks["token_trust"]:
            status = "BLOCKED_PENDING_TOKEN_ROTATION"
        elif not all(value for key, value in checks.items() if key != "opt_in"):
            status = "BLOCKED_INVALID_CONFIGURATION"
        elif not checks["opt_in"]:
            status = "READY_FOR_LIVE_SMOKE / AWAITING_OPERATOR_OPT_IN"
        else:
            status = "READY_FOR_LIVE_SMOKE"
        return {
            "status": status,
            "checks": checks,
            "mode": "outbound_only",
            "public_tls_and_routing": "NOT_TESTED",
        }

    def prepare(self):
        with self._lock:
            if self._prepared or self.preflight()["status"] != "READY_FOR_LIVE_SMOKE":
                raise LiveSmokeBlocked("smoke_preconditions_failed")
            # Validate the real adapter first; then fence it, before reserving any database.
            self._guard = LiveSmokeOutboundSender(
                provider="twilio", sender=self._sender, environment=self._controls
            )
            path = self._database_path()
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            try:
                descriptor = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
                )
            except OSError:
                raise LiveSmokeBlocked("smoke_database_not_fresh") from None
            os.close(descriptor)
            self._store = SqliteConversationStore(path)
            self._store.initialize()
            if not self._store.migrations_are_current() or not all(
                value == "ok" for value in self._store.sqlite_durability_checks().values()
            ):
                raise LiveSmokeBlocked("smoke_database_not_ready")
            self._prepared = True
        app = FastAPI(title="Twilio synthetic smoke callbacks")

        @app.get("/health")
        def health():
            return {"status": "ok", "smoke_id": self.smoke_id}

        @app.get("/ready")
        def ready():
            valid = not self._callback_failure.is_set() and self._store.migrations_are_current()
            return JSONResponse(
                {"status": "ready" if valid else "not_ready"}, status_code=200 if valid else 503
            )

        provider = TwilioProvider(
            auth_token=self._settings.twilio_auth_token,
            validate_signature=True,
            public_webhook_url=self._settings.twilio_public_webhook_url,
            public_status_callback_url=self._settings.twilio_status_callback_url,
        )

        @app.post("/webhooks/twilio/status")
        async def callback(request: Request):
            try:
                batch = provider.receive(
                    ProviderWebhookRequest(
                        "POST",
                        str(request.url),
                        dict(request.headers),
                        request.url.query.encode(),
                        request.headers.get("content-type", ""),
                        await request.body(),
                    )
                )
                if any(not isinstance(event, DeliveryStatusReceived) for event in batch.events):
                    raise InvalidWebhookPayload("Smoke accepts status events only")
                self._store.record_webhook_events(batch.events)
            except (
                InvalidWebhookSignature,
                InvalidWebhookPayload,
                PersistenceUnavailable,
            ) as error:
                self._callback_failure.set()
                code = (
                    403
                    if isinstance(error, InvalidWebhookSignature)
                    else (503 if isinstance(error, PersistenceUnavailable) else 400)
                )
                return Response(status_code=code)
            with self._lock:
                if not batch.events:
                    self._ignored_callbacks += 1
                for event in batch.events:
                    key = (
                        sha256(event.provider_message_id.encode()).hexdigest()[:12],
                        event.status.value,
                    )
                    if key in self._callback_events:
                        self._callback_duplicates += 1
                    self._callback_events.add(key)
            ack = provider.acknowledge()
            return Response(ack.body, media_type=ack.media_type, status_code=ack.status_code)

        return app

    def verify_public_callback(self, *, get=None):
        if not self._prepared:
            raise LiveSmokeBlocked("smoke_not_prepared")
        url = urlsplit(self._settings.twilio_status_callback_url)._replace(path="/health").geturl()
        try:
            response = (get or requests.get)(
                url, timeout=(3, 5), verify=True, allow_redirects=False
            )
            valid = response.status_code == 200 and response.json() == {
                "status": "ok",
                "smoke_id": self.smoke_id,
            }
        except (requests.RequestException, ValueError, TypeError, OSError):
            valid = False
        if not valid:
            raise LiveSmokeBlocked("smoke_public_callback_not_verified") from None
        self._callback_ready = True

    def submit_once(self):
        if not self._prepared or not self._callback_ready:
            raise LiveSmokeBlocked("smoke_callback_not_verified")
        with self._lock:
            if self._callback_failure.is_set():
                raise LiveSmokeBlocked("smoke_callback_invalid")
            if self._submitted:
                raise LiveSmokeBlocked("smoke_submission_limit")
            self._submitted = True
        self._timestamp = datetime.now(UTC).isoformat()
        claim = self._store.claim_generation(
            InboundMessage(
                "twilio",
                "SM" + self.smoke_id,
                "whatsapp:" + self._controls["TEST_WHATSAPP_RECIPIENT"],
                "whatsapp:" + self._controls["TWILIO_SMOKE_SENDER"],
                "Synthetic outbound-only smoke admission",
            )
        )
        self._inbound_id = claim.inbound_message_id
        if claim.owner_token is None or not self._store.complete_generation(
            inbound_message_id=claim.inbound_message_id,
            owner_token=claim.owner_token,
            reply_body="Teste RJ Studio AI",
            delivery_state=DeliveryState.PENDING,
        ):
            raise LiveSmokeBlocked("smoke_outbox_completion_failed")
        started = monotonic()
        OutboundDeliveryRunner(
            store=self._store,
            sender=self._guard,
            provider="twilio",
            timeout_seconds=self._settings.outbound_request_timeout_seconds,
            maximum_attempts=1,
        ).run_once()
        self._latency_ms = round((monotonic() - started) * 1000)
        return self.report()

    def report(self):
        delivery = (
            self._store.get_delivery_for_inbound(self._inbound_id) if self._inbound_id else None
        )
        accepted = delivery is not None and delivery.accepted_at is not None
        provider_id_hash = (
            sha256(delivery.provider_message_id.encode()).hexdigest()[:12]
            if (delivery and delivery.provider_message_id)
            else None
        )
        with self._lock:
            statuses = sorted(
                status for key, status in self._callback_events if key == provider_id_hash
            )
            duplicates = self._callback_duplicates
            ignored = self._ignored_callbacks
        failed = self._callback_failure.is_set() or (
            delivery and delivery.state == DeliveryState.FAILED
        )
        passed = accepted and bool(statuses) and not failed
        ambiguous = delivery and delivery.state in {DeliveryState.UNKNOWN, DeliveryState.SENDING}
        if self._callback_failure.is_set():
            result_class = "callback_invalid"
        elif failed:
            result_class = "delivery_failed" if accepted else "provider_rejected"
        elif passed:
            result_class = "provider_accepted"
        elif accepted:
            result_class = "accepted_callback_pending"
        elif ambiguous:
            result_class = "outcome_unknown"
        else:
            result_class = "not_submitted"
        return {
            "status": "LIVE_SMOKE_PASS" if passed else "LIVE_SMOKE_FAIL",
            "provider": "twilio",
            "mode": "outbound_only",
            "smoke_id": self.smoke_id,
            "timestamp": getattr(self, "_timestamp", None),
            "result_class": result_class,
            "provider_acceptance": None if ambiguous else accepted,
            "provider_id_hash": provider_id_hash,
            "final_state": delivery.state.value if delivery else None,
            "submissions": delivery.attempt_count if delivery else 0,
            "retries": 0,
            "duplicate_sends": 0,
            "callbacks": statuses,
            "duplicate_callbacks": duplicates,
            "ignored_callbacks": ignored,
            "submission_latency_ms": getattr(self, "_latency_ms", None),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Guarded one-message Twilio smoke; default check-only"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--callback-wait-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 0 <= args.callback_wait_seconds <= 60:
        print(json.dumps({"status": "BLOCKED_INVALID_CONFIGURATION", "reason": "smoke_bounds"}))
        return 2
    server = thread = driver = None
    # This process emits our allowlisted JSON only, never wire headers or noisy SDK logs.
    names = (
        "twilio.http_client",
        "urllib3",
        "urllib3.connectionpool",
        "requests",
        "uvicorn.error",
        "uvicorn.access",
        "dotenv.main",
    )
    old = {name: logging.getLogger(name).disabled for name in names}
    for name in names:
        logging.getLogger(name).disabled = True
    try:
        environment = {**dotenv_values(args.env_file), **os.environ}
        settings = Settings(
            _env_file=args.env_file,
            llm_provider="openai",
            openai_model="gpt-6.1-sol",
            openai_reasoning_effort="low",
            openai_max_output_tokens=1024,
            whatsapp_provider="twilio",
            delivery_mode="proactive",
        )
        driver = TwilioLiveSmoke(settings, environment, project_root=Path.cwd())
        result = driver.preflight()
        if args.execute and result["status"] == "READY_FOR_LIVE_SMOKE":
            app = driver.prepare()
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=args.port,
                    log_config=None,
                    access_log=False,
                    log_level="critical",
                )
            )
            thread = Thread(target=server.run, daemon=True)
            thread.start()
            deadline = monotonic() + 5
            while not server.started and thread.is_alive() and monotonic() < deadline:
                sleep(0.05)
            if not server.started:
                raise LiveSmokeBlocked("smoke_callback_server_unavailable")
            local = requests.get(
                f"http://127.0.0.1:{args.port}/ready", timeout=(3, 5), allow_redirects=False
            )
            if local.status_code != 200:
                raise LiveSmokeBlocked("smoke_callback_server_not_ready")
            driver.verify_public_callback()
            result = driver.submit_once()
            deadline = monotonic() + args.callback_wait_seconds
            while result["provider_acceptance"] and monotonic() < deadline:
                if (
                    result["final_state"] in {"read", "failed"}
                    or result["result_class"] == "callback_invalid"
                ):
                    break
                sleep(0.1)
                result = driver.report()
            evidence = driver._database_path().parent / "result.json"
            with os.fdopen(
                os.open(evidence, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
            ) as output:
                json.dump(result, output, indent=2)
        print(json.dumps(result, sort_keys=True))
        return (
            0
            if result["status"]
            in {
                "READY_FOR_LIVE_SMOKE",
                "LIVE_SMOKE_PASS",
                "READY_FOR_LIVE_SMOKE / AWAITING_OPERATOR_OPT_IN",
            }
            else 2
        )
    except Exception as error:
        # Never print provider exceptions, source input, credentials or arbitrary exception text.
        reason = str(error) if isinstance(error, LiveSmokeBlocked) else "smoke_operation_failed"
        try:
            result = driver.report() if driver is not None and driver._submitted else {}
        except PersistenceUnavailable:
            result = {
                "provider_acceptance": None,
                "submissions": None,
                "result_class": "local_evidence_unavailable",
                "retries": 0,
            }
        result.update(status="LIVE_SMOKE_FAIL", reason=reason)
        print(json.dumps(result, sort_keys=True))
        return 2
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        for name, disabled in old.items():
            logging.getLogger(name).disabled = disabled


if __name__ == "__main__":
    raise SystemExit(main())
