"""G0 cannot start solely by setting a purported safety flag."""

import socket

import pytest
from g0_staging_fixture import G0Staging, require_network_guard


def test_missing_guard_rejects_before_creating_database(tmp_path, monkeypatch):
    monkeypatch.delenv("TICKET13_NETWORK_GUARD", raising=False)
    with pytest.raises(RuntimeError, match="requires scripts/check_telnyx_offline"):
        G0Staging(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_forged_flag_without_socket_interception_fails_closed(monkeypatch):
    class UnprotectedSocket:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def connect(self, address):
            pass  # simulate an unguarded connection without performing any I/O

    monkeypatch.setenv("TICKET13_NETWORK_GUARD", "active")
    monkeypatch.setattr(socket, "socket", UnprotectedSocket)
    with pytest.raises(RuntimeError, match="guard is ineffective"):
        require_network_guard()
