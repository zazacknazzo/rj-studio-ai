"""Inspect the Linux network namespace before CI tests; no connection is attempted."""

import json
import subprocess

links = json.loads(subprocess.check_output(["ip", "-json", "link"], text=True))
if {link["ifname"] for link in links} != {"lo"}:
    raise SystemExit("Offline CI requires a namespace containing only loopback")
for family in ("-4", "-6"):
    routes = json.loads(
        subprocess.check_output(["ip", family, "-json", "route", "show", "default"], text=True)
    )
    if routes:
        raise SystemExit("Offline CI cannot have a default route")
print("Kernel network isolation verified: only loopback, no IPv4/IPv6 default routes")
