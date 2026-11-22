"""Prove Python network denial in fresh children, independently of caller env."""

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).parents[1] / "scripts/check_telnyx_offline.py"


@pytest.mark.parametrize(
    "operation",
    [
        "socket.socket(socket.AF_INET).connect(('198.51.100.1', 443))",
        "socket.socket(socket.AF_INET6).connect_ex(('2001:db8::1', 443))",
        "socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('198.51.100.1', 53))",
        "socket.socket(socket.AF_INET6, socket.SOCK_DGRAM).sendto(b'x', ('2001:db8::1', 53))",
        "socket.getaddrinfo('synthetic.invalid', 443)",
        "socket.gethostbyname('synthetic.invalid')",
        "socket.gethostbyname_ex('synthetic.invalid')",
        "socket.gethostbyaddr('198.51.100.1')",
        "socket.socket(socket.AF_INET).sendmsg([b'x'])",
    ],
)
def test_guard_denies_tcp_udp_dns_and_sendmsg_in_children(tmp_path, operation):
    guard = tmp_path / "guard"
    guard.mkdir(mode=0o700)
    (guard / "sitecustomize.py").write_text(runpy.run_path(str(RUNNER))["GUARD"])
    code = (
        "import socket,os\n"
        "assert os.environ['TICKET13_NETWORK_GUARD']=='active'\n"
        "try:\n    " + operation + "\n"
        "except RuntimeError as error:\n"
        "    assert str(error)=='TICKET13_IP_NETWORK_BLOCKED'\n"
        "else:\n    raise AssertionError('network guard did not deny')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={
            "PATH": os.defpath,
            "PYTHONPATH": str(guard),
            "HOME": str(tmp_path),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
