"""Local operator commands. Credentials and QR never appear in command output."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import webbrowser
from contextlib import suppress
from pathlib import Path

import httpx
from dotenv import dotenv_values

from rj_studio_ai.providers.waha import WahaAPI, phone_chat

ENV_PATH = Path(".env.b1")


def initialize(*, secondary=None, participants=()):
    if ENV_PATH.exists():
        raise ValueError("private_configuration_already_exists; edit .env.b1 privately")
    if secondary:
        phone_chat(secondary)
    for participant in participants:
        phone_chat(participant)
    if len(set(participants)) != len(participants) or len(participants) > 2:
        raise ValueError("at_most_two_distinct_participants")
    api_key = secrets.token_urlsafe(48)
    values = {
        "LLM_PROVIDER": "openai",
        "OPENAI_MODEL": "gpt-6.1-sol",
        "OPENAI_REASONING_EFFORT": "low",
        "OPENAI_MAX_OUTPUT_TOKENS": "1024",
        "OPENAI_API_KEY": "",
        "WAHA_SECONDARY_PHONE": secondary or "",
        "WAHA_AUTHORIZED_PHONES": json.dumps(list(participants)),
        "WAHA_API_KEY": api_key,
        "WAHA_API_KEY_SHA512": hashlib.sha512(api_key.encode()).hexdigest(),
        "WAHA_DASHBOARD_PASSWORD": secrets.token_urlsafe(32),
        "WAHA_WEBHOOK_SECRET": secrets.token_urlsafe(48),
        "WAHA_OPERATOR_TOKEN": secrets.token_urlsafe(48),
        "WAHA_JOURNAL_KEY": secrets.token_urlsafe(48),
    }
    with os.fdopen(os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        for key, value in values.items():
            f.write(key + "='" + value + "'\n")
    for directory in ("sessions", "backend", "control", "witness", "live-check"):
        path = Path(".local/b1") / directory
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    print("Created private .env.b1 (0600). Configure OPENAI_API_KEY and the secondary phone there.")


def config():
    if not ENV_PATH.exists() or ENV_PATH.stat().st_mode & 0o077:
        raise ValueError("private_env_missing_or_not_0600; run scripts/b1 init")
    return dict(dotenv_values(ENV_PATH))


def docker_environment():
    environment = os.environ.copy()
    # Do not change the user's default Docker context.
    colima_socket = Path.home() / ".colima/default/docker.sock"
    if not environment.get("DOCKER_HOST") and colima_socket.exists():
        environment["DOCKER_HOST"] = "unix://" + str(colima_socket)
    return environment


def compose(*args):
    command = ["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"]
    return subprocess.run(
        command + ["--env-file", str(ENV_PATH), "-f", "compose.b1.yaml", *args],
        env=docker_environment(),
        check=False,
    ).returncode


def api(values):
    return WahaAPI(base_url="http://127.0.0.1:3000", api_key=values["WAHA_API_KEY"])


def operator_request(values, action):
    with httpx.Client(trust_env=False) as client:
        response = client.request(
            "GET" if action == "ready" else "POST",
            "http://127.0.0.1:8001/" + ("ready" if action == "ready" else "ops/" + action),
            headers={"Authorization": "Bearer " + values["WAHA_OPERATOR_TOKEN"]},
            timeout=10,
        )
    return response.json()


def pair(values):
    secondary = values.get("WAHA_SECONDARY_PHONE")
    if not secondary:
        raise ValueError("configure_secondary_test_phone_in_private_env; never use the salon phone")
    phone_chat(secondary)
    from rj_studio_ai.waha_live import require_test_secondary

    require_test_secondary(secondary, Path("knowledge/rj_studio.yaml"))
    participants = json.loads(values["WAHA_AUTHORIZED_PHONES"])
    if not 1 <= len(participants) <= 2 or secondary in participants:
        raise ValueError("configure_distinct_authorized_participants")
    client = api(values)
    existing = client.request("GET", "/api/sessions/default")
    if existing.status_code == 404:
        payload = {
            "name": "default",
            "start": True,
            "config": {
                "ignore": {"groups": True, "channels": True, "status": True, "broadcast": True},
                "webjs": {"tagsEventsOn": False},
                "webhooks": [
                    {
                        "url": "http://backend:8000/webhooks/waha",
                        "events": ["message", "session.status"],
                        "hmac": {"key": values["WAHA_WEBHOOK_SECRET"]},
                        "retries": {"delaySeconds": 2, "attempts": 3, "policy": "constant"},
                    }
                ],
            },
        }
        response = client.request("POST", "/api/sessions", payload=payload, timeout=20)
        if response.status_code not in {200, 201}:
            raise ValueError("waha_session_creation_failed; see private local errors")
    elif existing.status_code == 200:
        info = existing.json()
        if info.get("me") and info["me"].get("id") != phone_chat(secondary):
            raise ValueError("connected_phone_mismatch; disconnect it before proceeding")
        if info.get("status") == "STOPPED":
            response = client.request("POST", "/api/sessions/default/start", timeout=20)
            if response.status_code not in {200, 201}:
                raise ValueError("waha_session_start_failed")
    else:
        raise ValueError("waha_unavailable")
    webbrowser.open("http://127.0.0.1:3000/dashboard")
    print("Open the local dashboard. Use admin and the private .env.b1 credentials.")
    print("Scan its QR with the SECONDARY phone. No QR or credentials are printed here.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lívia / WAHA private B1")
    parser.add_argument(
        "action",
        choices=(
            "init",
            "start",
            "waha",
            "backend",
            "pair",
            "status",
            "pause",
            "resume",
            "stop",
            "disconnect",
            "errors",
            "live-check",
        ),
    )
    parser.add_argument("--secondary")
    parser.add_argument("--participant", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            initialize(secondary=args.secondary, participants=args.participant)
            return 0
        values = config()
        if args.action in {"start", "waha", "backend"}:
            if args.action != "waha" and not values.get("WAHA_SECONDARY_PHONE"):
                raise ValueError("configure_WAHA_SECONDARY_PHONE_in_private_env")
            return compose(
                "up",
                "-d",
                "--build",
                *({"waha": ["waha"], "backend": ["backend"]}.get(args.action, [])),
            )
        if args.action == "pair":
            pair(values)
        elif args.action == "status":
            summary = {
                "openai_key_configured": bool(values.get("OPENAI_API_KEY")),
                "egress": False,
                "egress_blockers": ["AUD-01", "AR-02"],
            }
            try:
                info = api(values).session_info()
                summary["session_status"] = info.get("status")
                summary["secondary_matches"] = bool(values.get("WAHA_SECONDARY_PHONE")) and (
                    info.get("me") or {}
                ).get("id") == phone_chat(values["WAHA_SECONDARY_PHONE"])
            except Exception:
                summary["session_status"] = "unavailable"
            try:
                summary["backend"] = operator_request(values, "ready")
            except Exception:
                summary["backend"] = "unavailable"
            print(json.dumps(summary, indent=2))
        elif args.action in {"pause", "resume"}:
            print(json.dumps(operator_request(values, args.action)))
        elif args.action == "stop":
            with suppress(Exception):
                operator_request(values, "pause")
            return compose("stop")
        elif args.action == "disconnect":
            with suppress(Exception):
                operator_request(values, "pause")
            response = api(values).request("POST", "/api/sessions/default/logout", timeout=20)
            if response.status_code not in {200, 201}:
                raise ValueError("waha_logout_failed")
            print("Secondary session disconnected; inference paused; egress remains blocked.")
        elif args.action == "errors":
            # The launcher intentionally never prints raw container logs.
            print(json.dumps(operator_request(values, "ready"), indent=2))
            print(
                "Private raw logs: docker-compose --env-file .env.b1 "
                "-f compose.b1.yaml logs --tail 30 backend"
            )
        elif args.action == "live-check":
            from rj_studio_ai.waha_live_check import run_live_check

            return run_live_check()
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # Never echo arbitrary remote text, Pydantic inputs or credential values.
        if isinstance(error, ValueError) and len(str(error)) < 180:
            print(str(error), file=sys.stderr)
        else:
            print(
                "B1 command failed: " + type(error).__name__ + ". Run scripts/b1 status.",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
