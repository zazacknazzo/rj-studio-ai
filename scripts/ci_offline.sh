#!/usr/bin/env bash
set -euo pipefail
test_python="$1"
"$test_python" -I scripts/assert_no_external_network.py
"$test_python" -m ruff check .
"$test_python" -m ruff format --check .
"$test_python" -m compileall -q src tests scripts
"$test_python" -m pip check
"$test_python" -m pip inspect > work/pip-inspect.json
git diff --check
"$test_python" scripts/check_telnyx_offline.py --python "$test_python" --output work/ci-tests
