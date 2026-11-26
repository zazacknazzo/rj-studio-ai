from types import SimpleNamespace

import pytest

from rj_studio_ai import waha_private_cli as cli


def test_start_uses_existing_session_once(monkeypatch):
    states = iter(("STOPPED", "STOPPED", "STARTING", "WORKING"))
    starts = []

    def request(method, path, *, timeout):
        starts.append((method, path))
        return SimpleNamespace(is_success=True)

    client = SimpleNamespace(session_info=lambda: {"status": next(states)}, request=request)
    monkeypatch.setattr(cli, "sleep", lambda _: None)
    cli.wait_for_session(client)
    assert starts == [("POST", "/api/sessions/default/start")]


def test_qr_requires_operator():
    client = SimpleNamespace(session_info=lambda: {"status": "SCAN_QR_CODE"})
    with pytest.raises(ValueError, match="requires_operator"):
        cli.wait_for_session(client)


def test_start_of_active_window_preserves_inflight_work(monkeypatch):
    monkeypatch.setattr(cli, "config", lambda: {})
    monkeypatch.setattr(cli, "api", lambda _: object())
    monkeypatch.setattr(cli, "wait_for_session", lambda _: None)
    actions = []

    def operator(_, action):
        actions.append(action)
        return {"mode": "temporary_private_test", "egress": True, "connected_secondary": True}

    monkeypatch.setattr(cli, "operator_request", operator)
    cli.main("start")
    assert actions == ["ready"]


def test_failed_activation_pauses_and_exits_with_error(monkeypatch):
    actions = []

    def operator(_, action):
        actions.append(action)
        return {"paused": False} if action == "resume" else {"detail": "denied"}

    monkeypatch.setattr(cli, "config", lambda: {})
    monkeypatch.setattr(cli, "operator_request", operator)
    with pytest.raises(ValueError, match="activation_denied"):
        cli.main("resume")
    assert actions == ["resume", "waha/private-test/start", "pause"]
