"""Local controls for the bounded WAHA test. Never print provider responses."""

import json
import sys
from time import monotonic, sleep

import httpx

from rj_studio_ai.providers.base import OutboundOutcomeUnknown, OutboundPermanentError
from rj_studio_ai.waha_cli import api, config, operator_request


def wait_for_session(client, *, timeout=120):
    deadline = monotonic() + timeout
    requested = False
    while monotonic() < deadline:
        try:
            state = client.session_info().get("status")
        except (OutboundOutcomeUnknown, OutboundPermanentError):
            sleep(1)
            continue
        if state == "WORKING":
            return
        if state == "STOPPED" and not requested:
            response = client.request("POST", "/api/sessions/default/start", timeout=20)
            if not response.is_success:
                raise ValueError("waha_session_start_failed")
            requested = True
        elif state not in {"STOPPED", "STARTING"}:
            raise ValueError("waha_session_requires_operator")
        sleep(1)
    raise ValueError("waha_session_start_timeout")


def wait_for_backend(values):
    deadline = monotonic() + 30
    while monotonic() < deadline:
        try:
            ready = operator_request(values, "ready")
        except httpx.TransportError:
            sleep(1)
            continue
        if ready.get("mode") != "temporary_private_test":
            raise ValueError("private_backend_unavailable")
        return ready
    raise ValueError("private_backend_start_timeout")


def main(action):
    values = config()
    if action == "status":
        print(json.dumps(operator_request(values, "ready"), indent=2))
        return
    if action == "pause":
        result = operator_request(values, "pause")
        if result.get("paused") is not True:
            raise ValueError("private_test_pause_failed")
        print(json.dumps(result))
        return
    if action == "start":
        wait_for_session(api(values))
        ready = wait_for_backend(values)
        if ready.get("egress") and ready.get("connected_secondary"):
            print(json.dumps({"active": True, "scope": ready["mode"]}))
            return
    result = operator_request(values, "resume")
    if result.get("paused") is not False:
        raise ValueError("waha_identity_or_resume_failed")
    try:
        result = operator_request(values, "waha/private-test/start")
        if result.get("active") is not True:
            raise ValueError("private_test_activation_denied")
    except Exception:
        operator_request(values, "pause")
        raise
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except (ValueError, httpx.HTTPError, OutboundOutcomeUnknown):
        sys.exit("Operação indisponível. Confira a sessão, a identidade e a janela do teste.")
