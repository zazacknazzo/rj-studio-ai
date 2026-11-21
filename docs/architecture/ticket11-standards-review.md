# Ticket 11 — Independent Standards Review

Date: 2026-11-21, America/Sao_Paulo. Reviewer: independent Standards subagent.
Scope: direct inspection and execution against baseline
`07c1b7dc150d7eb1776b97d891cd29347adffd37`, branch
`codex/telnyx-coexistence-11-sender`. Production code initially inspected at CP3
`a7825b94d9cc0a757f37e5cd5243c1ec9c843714`; CP4 tests were finalized during review.
HEAD after execution: `2751652a3df39e0bf3f0d5c7588172b510eab0db`.
No implementer validation report was used as a substitute for code or test evidence.
The reviewer changed only this document; primary agent remains sole Git writer.

## Verdict

**PASS for the corrected OFFLINE scope after supplemental verification below.** The
initial Standards perspective did not identify the optional-schema P2 subsequently
found by the independent Spec/adversarial reviews, or the later provider-default P2
found by Spec. That omission is acknowledged;
the initial229-test run alone was insufficient to detect it. This is a Standards
review recommendation for direct orchestrator audit, not approval of real sending.
**Operational/production: NO-GO.** AUD-01 remains open: an old, structurally valid
SQLite copy can erase later fences. The documented outside-snapshot quarantine and
reconciliation are requirements, not implemented protection.

## Direct inspection

Read AGENTS.md and local issue/domain instructions, the actual baseline diff,
Ticket11 spec/ADR0019 and production code at these seams:

- `telnyx_request.py`: deterministic UTF8 body, fixed method/scheme/host/path and empty
  query, immutable request objects, UUIDv4, HMAC input includes organization/profile,
  channel/recipient/modality/key/bytes; repr hides request and integrity key.
- `providers/telnyx_sender.py`: injected-only exchange, no default client or Telnyx SDK,
  explicit connect/read budgets, retries=0 and redirects=false; strict subset of the
  official response fields, fixed outcome classifications, no body/error logging.
- `delivery.py` and `persistence.py`: preparation before authorization, existing
  BEGIN IMMEDIATE assessment repeated, exact request identity added in same writer
  as markers, exchange after commit, conservative unknown after possible submission.
  A valid HTTP acceptance does not advance sent/delivered/read; ledger still owns it.
- Migration0022 and schema inspection: additive table, no parent-table rebuild or
  historical proof backfill; immutable/replacement guards; retained identity survives
  delivery purge, UUID rather than reusable numeric delivery ID is the identity.
- Config/main: provider Literal remains meta/twilio and production selection contains
  no Telnyx constructor, route or activation. Meta/Twilio modules and intelligence
  files are absent from this diff. Dev pytest range changed; runtime declarations did
  not change.

`send_prepared` is a low-level adapter seam whose trusted caller must first commit
store authorization. It is not a public authorization boundary or proof that an
arbitrary injected callable respects budgets/no-network policy. The reviewed concrete
runner follows that contract. No operational composition/credentials are supplied.

The new keyed integrity metadata does not erase baseline T10 unkeyed fingerprints,
provide anonymity, detect a stale restore, or define retention/erasure. Retained request
receipts join CX-01. Stable external integrity-key custody/rotation/loss handling and
verified organization/credential association remain future operational composition gates.

## Executed independently

Environment: shared isolated toolchain, independently executed commands; the reviewer
did not rebuild a second venv. Python3.12.14, SQLite3.53.1, pip26.3, pytest9.2.0,
Ruff0.17.6, pip-audit2.10.1. Inspected `/tmp/ticket11/run` and its sitecustomize guard
before execution. Wrapper uses env-i, no commercial environment/.env, private temp,
PYTEST_DISABLE_PLUGIN_AUTOLOAD and Python IP guard inherited by children.
Verified parent/child socket attempts were blocked before connection, and GH_TOKEN,
TELNYX_API_KEY, OPENAI_API_KEY and ANTHROPIC_API_KEY were absent. This is Python-level
IP isolation, not a kernel sandbox for arbitrary native executables.

```bash
/tmp/ticket11/run -m pytest \
  tests/test_telnyx_request.py tests/test_telnyx_sender.py \
  tests/test_telnyx_sender_integration.py tests/test_telnyx_http_migration.py \
  tests/test_telnyx_sender_adversarial.py tests/test_telnyx_submission_migration.py \
  tests/test_telnyx_submission.py tests/test_outbound_delivery.py \
  tests/test_delivery_status.py \
  --basetemp=/tmp/ticket11/tmp/standards -ra
```

**229 passed, 0 skipped, 84.22s, exit0.** These are overlapping modules with the
implementer suite; do not sum counts as distinct coverage. The known-gap restore tests
passing reproduces AUD-01, not its remediation. SQLite real, all exchanges intercepted.

Three additional probes authored and executed independently (source below):

```bash
/tmp/ticket11/run -m pytest /tmp/ticket11/standards-probes.py \
  --basetemp=/tmp/ticket11/tmp/standards-probes -ra
```

**3 passed, 0 skipped, 11.14s, exit0.** They verify store-level key rotation denial
without marker, a forbidden host even with a recomputed MAC, and the exact retained-key
SQL guard after purge rather than relying on a different uniqueness/FK failure.

Additional commands actually executed:

| Check | Observed result |
| --- | --- |
| `pip check` through sanitized wrapper | No broken requirements, exit0 |
| Ruff check of changed production modules and migrations | All checks passed |
| Ruff format --check of same scope | 29 files already formatted |
| `stat -c '%a %n'` on parent/temp/standards basetemp | Each0700 |
| Parent and subprocess Python IP guard probe | Both blocked, exit0 |
| `git diff <baseline> --name-only` and current HEAD/status | Inspected directly; no reviewer code mutations |

## Independent probe source

Save as `/tmp/ticket11/standards-probes.py` after recreating the private environment
and guard documented by the ticket handoff/validation instructions. It uses only
synthetic fixtures, SQLite and an intercepted exchange. No HTTP client is constructed.

```python
"""Independent Standards probes; synthetic SQLite, intercepted exchange only."""

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import ingress as ingress, TIME
from test_telnyx_request import signer as signer
from test_telnyx_submission import prepare, outbound
from test_telnyx_sender import acceptance, response
from test_telnyx_sender_integration import runner
from test_telnyx_delivery_status import pending
from rj_studio_ai.telnyx_request import bind_http_request
from rj_studio_ai.persistence import DeliveryState


def test_key_rotation_cannot_overwrite_existing_request_before_marker(ingress, signer):
    store, _, claim = prepare(ingress)
    request = signer.prepare(outbound(claim))
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        assert bind_http_request(db, request, request.message)
    rotated = replace(signer, integrity_key=b"new-synthetic-integrity-key-00000")
    changed = rotated.prepare(request.message)
    assert changed.request_mac != request.request_mac
    assert not store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=changed.message,
        http_request=changed,
        now=TIME,
    )
    assert store.get_delivery(claim.delivery_id).first_submission_at is None
    assert store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=request.message,
        http_request=request,
        now=TIME,
    )


def test_host_allowlist_rejects_even_a_recomputed_valid_mac(ingress, signer):
    store, _, claim = prepare(ingress)
    request = replace(signer.prepare(outbound(claim)), host="attacker.invalid")
    request = replace(request, request_mac=signer._mac(request))
    assert not signer.verify(request)
    assert not store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=request.message,
        http_request=request,
        now=TIME,
    )
    assert store.get_delivery(claim.delivery_id).first_submission_at is None
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM telnyx_http_requests").fetchone() == (0,)


def test_retained_old_uuid_cannot_reappear_after_purge_as_a_new_insert(ingress, signer):
    _, store, _ = ingress
    pending(store)
    first = runner(store, signer, lambda r, **_: response(acceptance(r))).run_once(now=TIME)
    assert first.state is DeliveryState.ACCEPTED
    store.purge_messages_older_than(TIME + timedelta(days=1))
    pending(store, message_id="standards-after-purge")
    with store._connect() as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(outbound_deliveries)")]
        row = list(db.execute("SELECT * FROM outbound_deliveries").fetchone())
        row[columns.index("id")] += 50
        row[columns.index("outbound_message_id")] += 50
        row[columns.index("submission_key")] = first.submission_key
        sql = (
            "INSERT INTO outbound_deliveries("
            + ",".join(columns)
            + ") VALUES("
            + ",".join("?" for _ in row)
            + ")"
        )
        with pytest.raises(sqlite3.IntegrityError, match="^HTTP identity cannot be reused$"):
            db.execute(sql, row)
        assert db.execute("SELECT COUNT(*) FROM telnyx_http_requests").fetchone() == (1,)
```

## Findings and limits

The initial Standards review confirmed no P0/P1/P2; the later independent
Spec/adversarial review identified a response-schema P2 that this perspective missed.
The correction and supplemental execution below leave no confirmed P1/P2 outstanding
in the reviewed corrected offline paths. The suite and own
probes support deterministic binding, immutable identity/purge behavior, preservation
of existing gates, conservative outcome persistence and legacy regressions. They do
not prove all scheduler interleavings or storage failure modes.

AUD-01 and CX-01/06/11/15/16/17/19/24/29/30/32/33/35/36/37 retain their applicable
operational/audit gates; this review closes no checkbox. Positive channel fixtures are
synthetic, and the implementation provides no activation override. No production-ready
claim is supported. Local pytest9 compatibility was executed; advisory scanning and
full-suite results belong to the principal's own evidence unless independently rerun.

Not executed by this reviewer: integral pytest, Gitleaks, pip-audit, compileall, remote
GitHub issue mutation, live Telnyx/API, real credentials, real restore release, account
sync, hardware crash/power loss, deployment or pilot. Full-suite/scanner evidence must
be reported separately by its actual executor. No real-world delivery was simulated
as observed evidence; fake response outcomes remain explicitly offline simulations.

## Supplemental verification after independent findings

Spec/adversarial reviewers, not this Standards reviewer, identified that identity-valid
HTTP200 could still contain malformed **known optional** response fields. The original
Standards perspective missed that gap. After their findings, I directly inspected the
actual production/test diff from CP4 and independently reran the corrected paths.
No report text was accepted as a substitute for this supplemental execution.

The correction checks present sender status/line_type enums; sender and recipient
carrier/line_type scalar types where applicable; encoding and opaque callback-data
strings; timezone-qualified, calendar-valid received_at; finite numeric-or-null
wait_seconds with boolean rejected; and contradictory known non-text body variants.
Unknown additional fields remain forward compatible. Invalid responses become a fixed
unknown outcome. Additional changes enforce canonical profile UUID before building a
request and avoid overflow/underflow in timeout partition arithmetic. The shared
synthetic profile fixture now uses a valid UUID. I inspected those production and
focused-test changes directly; I did not edit them.

```bash
/tmp/ticket11/run -m pytest tests/test_telnyx_request.py \
  tests/test_telnyx_sender.py tests/test_telnyx_sender_integration.py \
  --basetemp=/tmp/ticket11/tmp/standards-supplement -ra
/tmp/ticket11/run -m pytest /tmp/ticket11/standards-probes.py \
  --basetemp=/tmp/ticket11/tmp/standards-probes-supplement -ra
```

Actual results: **117 passed, 0 skipped,18.10s,exit0**; own three probes reexecuted:
**3 passed,0 skipped,11.47s,exit0**. Ruff check and format--check on the two corrected
production modules and three focused test modules also passed (**5 files formatted**).
These runs overlap the original229 and the implementer's suite; counts are not additive.

Corrected production bytes inspected/executed before their next publication:

| File | SHA256 |
| --- | --- |
| `telnyx_request.py` | `4697d82edb594a57e70dffed862f81470e893750e3d51727b25aafc253b0ddb4` |
| `providers/telnyx_sender.py` | `632460d157efb954a1897bea49562a38ee71e688eec73ffe653d48dd25aeb849` |

No new P1/P2 was confirmed in this supplemental inspection/execution. This is an
offline recommendation only. AUD-01, external quarantine/reconciliation, actual
credential-organization association and all operational gates remain unchanged.

## Final candidate — provider-default isolation fix

Independently inspected commit `a049753205001d81a9ac0f11253eab5760a2f017`
directly with git show. The independent **Spec reviewer**, not Standards, found that
constructing a concrete Telnyx runner with the real provider=None default could claim
and consume legacy-provider work before its local preparation failure. The earlier
Standards selection did not detect this gap; its helper supplied provider=telnyx.

The shared provider-normalization helper now runs in runner and executor construction:
a concrete Telnyx sender with None becomes telnyx; explicit incompatible provider
raises before any claim; other sender behavior is preserved. I inspected this control
flow and independently executed only the two new parametrized legacy-outbox cases,
without repeating the full suite:

```bash
/tmp/ticket11/run -m pytest \
  tests/test_telnyx_sender_integration.py::test_concrete_sender_default_provider_preserves_other_outboxes \
  --basetemp=/tmp/ticket11/tmp/standards-final-provider -ra
```

Observed: **2 passed,0 skipped,8.05s,exit0**. Each verifies repeated default-runner polls
leave a Meta/Twilio outbox pending with zero attempts, both constructors reject explicit
mismatches, and an unstarted default executor is normalized. No transport was invoked.
The corrected final candidate remains **PASS for reviewed offline scope**, with no
confirmed P1/P2 remaining from this perspective. Operational/production stays **NO-GO**;
AUD-01 and the previously recorded operational gates remain open. No code/test changes,
commits or pushes were made by this reviewer.
