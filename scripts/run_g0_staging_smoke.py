"""Run the synthetic G0 demo using the existing sanitized, socket-blocked test runner.

Requires an installed dev venv. No server, account, env file or transport options.
"""

import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new private evidence directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    python = args.python.absolute()
    output = args.output.absolute()
    result = subprocess.run(
        [
            str(python),
            str(root / "scripts/check_telnyx_offline.py"),
            "--python",
            str(python),
            "--output",
            str(output),
            "tests/test_g0_staging_smoke.py",
        ],
        cwd=root,
        check=False,
    )
    if result.returncode:
        return result.returncode
    reports = [
        json.loads(path.read_text()) for path in sorted((output / "run").glob("*/g0-report.json"))
    ]
    # pytest's current aliases are symlinks; each real scenario has exactly one report.
    reports = {report["scenario"]: report for report in reports}
    if len(reports) != 22:
        raise RuntimeError("G0 evidence is incomplete")
    destination = output / "g0-report.json"
    destination.write_text(
        json.dumps(
            {
                "scope": "synthetic staging only; no real LLM or WhatsApp",
                "real_ingress_decision": "NO-GO pending audit and deployment evidence",
                "real_egress_decision": "NO-GO; AUD-01/AR-02 OPEN",
                "scenarios": list(reports.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(f"Synthetic evidence: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
