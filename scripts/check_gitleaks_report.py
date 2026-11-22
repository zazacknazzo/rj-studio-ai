"""Explicit triage of three unchanged baseline false positives; never hide new hits."""

import hashlib
import json
import sys
from pathlib import Path

# Public schema digest, evaluation prose, and synthetic operator hash; inspected T11/T12/T13.
KNOWN = {
    "docs/architecture/v1-ticket11-validation.md": {
        "line": 53,
        "sha256": "b94905417ae1b0138b1ed4abe2e15772510b4f96a7c005e650e0e7a16c861f12",
        "rule": "generic-api-key",
    },
    "docs/evals/V1/openai-partial-2026-10-02.md": {
        "line": 11,
        "sha256": "c205de8e523c3c0122874352a64fb06960feca52df873c42564c4df4847199c1",
        "rule": "generic-api-key",
    },
    "tests/test_telnyx_authentication.py": {
        "line": 32,
        "sha256": "9ae8f381b0ac9ca840556701e1dc71205de3d30d571764d37a215370a42ffc78",
        "rule": "generic-api-key",
    },
}


def main():
    findings = json.loads(Path(sys.argv[1]).read_text())
    for finding in findings:
        path = Path(finding["File"])
        name = path.as_posix().removeprefix("./")
        expected = KNOWN.get(name)
        if not expected or (
            finding["StartLine"] != expected["line"]
            or finding["RuleID"] != expected["rule"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]
        ):
            raise SystemExit("New or changed secret-scan finding requires independent triage")
    print(f"Raw Gitleaks findings: {len(findings)}; unchanged baseline false positives only")


if __name__ == "__main__":
    main()
