"""Reproduce offline checks in a credential-free child with Python IP sockets blocked.

Use an already installed isolated venv: python scripts/check_telnyx_offline.py
--python /path/to/venv/bin/python [--output /new/private/directory] [pytest selections].
This is test-process isolation, not a kernel network sandbox or runtime composition.
"""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

GUARD = """import os
import socket
for name in ("connect", "connect_ex", "sendto", "sendmsg", "send", "sendall", "bind", "listen"):
    original = getattr(socket.socket, name, None)
    if original is None:
        continue
    def guard(sock, *args, _original=original, **kwargs):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError("TICKET13_IP_NETWORK_BLOCKED")
        return _original(sock, *args, **kwargs)
    setattr(socket.socket, name, guard)
def no_dns(*args, **kwargs):
    raise RuntimeError("TICKET13_IP_NETWORK_BLOCKED")
for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    setattr(socket, name, no_dns)
os.environ["TICKET11_NETWORK_GUARD"] = "active"
os.environ["TICKET13_NETWORK_GUARD"] = "active"
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("selection", nargs="*")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.output is None:
        work = Path(tempfile.mkdtemp(prefix="ticket13-offline-"))
    else:
        work = args.output.resolve()
        work.mkdir(mode=0o700)  # refuse existing paths; pytest may clear its own basetemp
    work.chmod(0o700)
    for name in ("home", "tmp", "guard"):
        (work / name).mkdir(mode=0o700)
    (work / "guard" / "sitecustomize.py").write_text(GUARD)
    python = args.python.absolute()
    env = {
        "PATH": str(python.parent) + os.pathsep + os.defpath,
        "HOME": str(work / "home"),
        "TMPDIR": str(work / "tmp"),
        "LANG": "C.UTF-8",
        "PYTHONPATH": os.pathsep.join(
            str(p) for p in (work / "guard", root / "src", root / "tests")
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    print(f"Private evidence directory: {work}", flush=True)
    return subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            "-ra",
            "-o",
            "junit_family=xunit1",
            "--basetemp",
            str(work / "run"),
            "--junitxml",
            str(work / "pytest.xml"),
            *args.selection,
        ],
        cwd=root,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
