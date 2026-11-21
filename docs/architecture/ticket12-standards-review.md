# Ticket12 — independent Standards Review

Date: 2026-11-21 (America/Sao_Paulo). Reviewed baseline
`246fe79a9bed4b202c49d3b2780320f6d5a0ca9c` against the Ticket12 branch plus
CP5 working changes. Commit at initial review start:
`f55d7f51ef72bcf659de6b0ffe3faec0308e185f`. CP5 source/test candidate independently confirmed:
`d7b5d72a2e784ec954bf4f100eac9d4eaba7a1dc`. Final source/test candidate after
HTTP204 framing cleanup independently confirmed at local HEAD and origin branch:
`533052f2d60ee43bd66e82170af1801f4523c76a`.
`git diff 533052f2d60ee43bd66e82170af1801f4523c76a -- src tests` was empty. Reviewer did not edit source/tests,
commit, push, use commercial credentials, invoke Telnyx or start workers.

**Offline opinion:** eligible for direct orchestrator audit after the two reproduced
candidate defects below were corrected and independently rechecked. No new P1/P2
confirmed pending in this Standards scope on the corrected working candidate.
**Production opinion: NO-GO.** AUD01 remains OPEN; closed offline composition is
not an operational antirollback system. This review is not release approval or
real-provider validation.

## Direct inspection

Read AGENTS.md, Ticket12 spec/ADR0020, relevant prior request/ingress/SQLite seams,
actual diff, raw HTTP/ASGI code and tests. Inspected schema/readiness, local-counter
privacy, inherited transaction and exact-request authorization, isolated factory,
production route/provider exclusion and handoff. The reviewer ran its own commands
and probes; primary-reported outcomes are not attributed to this reviewer.

- Scope remains single-business; no new tenant framework, salon facts, LLM policy,
  main/provider runtime enablement, Meta/Twilio adapter or Baileys change was found
  in the reviewed diff. Changes to older tests update only the current head to0023,
  preserving historical interrupted revision expectations and integrity assertions.
- Original bytes are bounded before buffering; authentication header duplicates
  are rejected before constructing the selected header dictionary. Size enforcement
  uses actual streamed bytes even without an honest Content-Length. Header cardinality
  and total bytes are bounded. The existing authenticator verifies signature before
  JSON/scope; no successful empty batch was introduced.
- Known event/effect receipts precede204. SQLite busy wait shares the work deadline;
  precommit/postcommit checks preserve retry safety. Failed/late commit cannot prove
  timely ACK. Fsync and actual ASGI/server/socket backpressure remain unproved bounds.
- Unsupported contracts return non2xx; the durable counter has only reason/count/
  local first/last time, not text, raw body, hash, routing/event IDs or secret. Its
  finite-label count is an observation count, including retries, not deduped messages.
  Finite process response/bucket metrics do not accumulate latency samples. Counter
  retention, alerts and operational diagnostics remain limited and explicitly scoped.
- Readiness exposes all six requested dimensions; health/ingress/persistence never
  imply operational channel, generation or egress readiness. Factory supplies a
  quarantined store outside the restored DB and composes no workers/release API.
- Strict optional store signer verifies prepared request before inherited writer
  authorization; default internal compatibility remains. Constructor guard added in
  review prevents public offline-composition construction with an unfenced store.
  This trusts process configuration, not arbitrary hostile Python/SQLite writers.

## Findings reproduced and correction evidence

| ID | Priority | Reproduction on initial WIP | Correction independently verified |
| --- | --- | --- | --- |
| STD12-01 | P2, late successful ACK | Set injected monotonic clock to2.0 inside metrics.record after the last deadline check. At http.response.start, captured(204,2.0), violating the1.5s application deadline. Metrics' lock also sat before final send. | Metrics moved into finally after response emission. Same interleaving captures(204,0.0), then metrics advances clock to2.0. No metrics lock remains between final deadline check and response helper. |
| STD12-02 | P2, composition invariant bypass | Construct OfflineTelnyxASGI(settings, ordinary_store, ...). Readiness claimed quarantined=True, yet exposed store authorized Telnyx with http_request omitted using a valid legacy claim. Approved factory was safe, but direct constructor silently accepted incompatible composition. | Constructor rejects a store whose process quarantine flag is notTrue. Same direct construction now raisesValueError. The legacy lower-level store remains compatible, explicitly outside offline composition. |

Both are defects in the evolving candidate, not evidence that a production endpoint
was enabled or that a real send occurred. They do not close AUD01/CX35 operational
gates. Corrected tests were executed independently; this report does not infer
closure from primary assurances.

## Independently executed checks

All tests used `/tmp/ticket12/venv/bin/python` through the committed
`scripts/check_telnyx_offline.py`: new private0700 evidence parent, credential-free
child environment, Python IP socket guard including children. This is not a kernel
network sandbox. Venv installation and external dependency audit belong to primary
validation, not an independently performed install/audit here.

```bash
python scripts/check_telnyx_offline.py --python /tmp/ticket12/venv/bin/python \
  --output /tmp/ticket12/standards-focused-final \
  tests/test_telnyx_http.py tests/test_telnyx_asgi.py \
  tests/test_telnyx_asgi_durability.py tests/test_telnyx_asgi_observability.py \
  tests/test_telnyx_asgi_egress.py tests/test_telnyx_asgi_load.py \
  tests/test_migrations.py tests/test_telnyx_http_migration.py
```

Corrected focused result: **96 passed,2warnings,20.40s**, exit0.
Two warnings are pytest record_property versus xunit2; properties are still present
in the produced JUnit. They are not test failures and are not silently called absent.
The8-way load JUnit properties independently measured128unique requests: p95
0.18849s, p99 0.44526s, max0.53411s,128x204;128duplicate requests: p95 0.06386s,
p99 0.13865s, max0.19872s,128x204. Both recorded zero late successes. These samples
use real SQLite WAL/FULL and in-process ASGI, without provider/proxy/network latency.
This is a focused suite; the reviewer did not run a complete suite at this stage.
Ruff check, Ruff format--check(327files) and git diff--check independently passed.

Own corrected defect reproductions: **2passed2.95s**, exit0, evidence
`/tmp/ticket12/standards-corrected-probe-evidence/pytest.xml`.
Own migration0023 post-DDL failure probe: **1passed2.69s**, exit0, evidence
`/tmp/ticket12/standards-migration23-evidence/pytest.xml`. This probe starts with
historicalunknown data at0022, injects a failure after CREATE TABLE executes,
verifies table/version rollback and unchanged history, then completes migration
and verifies current schema/history. No rows were deleted to obtain a green test.

Initial own focused run: **3failed93passed2warnings18.75s**. One test referenced
nonexistent TelnyxRequest.body before exercising the negative (corrected to actual
content field); two load cases encountered SQLite contention at0.05s busy timeout:
unique requests96x204/32x503, duplicate requests123x204/5x503. No late-success assert
failed. The primary increased bounded busy timeout to0.5s within1.35s work budget;
the same corrected focused selections, including both8-way load cases, passed.
These are measured synthetic-host results, not a provider SLA or CI guarantee.
The first defect probe run reported3passed2.95s because it included one no-op
scaffolding case; only the two substantive probes are evidence, and the clean
corrected run contains exactly those two. No-op was not counted as security coverage.

## Reproducible independent probe sources

Save this block to a temporary test module and run it via the same offline runner
with a fresh --output path. It exercises the corrected behavior and0023 failure.
The fixture imports refer to the repository's synthetic tests, not commercial data.

```python
import asyncio
import sqlite3
import pytest
from alembic import command
from sqlalchemy import event
from sqlalchemy.engine import Engine
from test_telnyx_authentication import NOW, signed
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_messages import ingress as ingress, wire, TIME
from test_telnyx_submission import prepare, outbound
from test_telnyx_submission_migration import baseline, snapshot, assert_preserved
from rj_studio_ai.telnyx_asgi import OfflineTelnyxASGI, create_telnyx_offline_app


def test_metrics_cannot_delay_success(settings, private_key, tmp_path):
    ticks = [0.0]
    app = create_telnyx_offline_app(
        settings,
        tmp_path / "late.db",
        wall_clock=lambda: NOW,
        monotonic_clock=lambda: ticks[0],
    )
    original = app.metrics.record

    def record(*args):
        original(*args)
        ticks[0] = 2.0

    app.metrics.record = record
    statuses = []

    async def run():
        req = signed(private_key, wire())
        pending = [req.body]

        async def receive():
            return {"type": "http.request", "body": pending.pop(), "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append((message["status"], ticks[0]))

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/webhooks/telnyx",
                "headers": [
                    (b"content-type", b"application/json"),
                    *[(k.encode(), v.encode()) for k, v in req.headers.items()],
                ],
            },
            receive,
            send,
        )

    asyncio.run(run())
    assert statuses == [(204, 0.0)]
    assert ticks[0] == 2.0


def test_unfenced_composition_denied(ingress, settings):
    store, path, claim = prepare(ingress)
    with pytest.raises(ValueError):
        OfflineTelnyxASGI(settings, store, wall_clock=lambda: NOW, clock=lambda: 0.0)
    # Lower-level compatibility does not become a composition bypass.
    assert store.authorize_delivery_submission(
        delivery_id=claim.delivery_id,
        owner_token=claim.owner_token,
        message=outbound(claim),
        now=TIME,
    )


def test_0023_post_ddl_rollback(tmp_path, monkeypatch):
    path = tmp_path / "migration.db"
    manager = baseline(path, monkeypatch, outcome="unknown")
    original = command.upgrade
    with monkeypatch.context() as patch:
        patch.setattr(command, "upgrade", lambda cfg, _: original(cfg, "0022_telnyx_http_identity"))
        manager.upgrade()
    before = snapshot(path)

    def fail_after_table(_, __, statement, *___):
        if "CREATE TABLE telnyx_ingress_rejections" in statement:
            raise RuntimeError("synthetic post-DDL failure")

    event.listen(Engine, "after_cursor_execute", fail_after_table)
    try:
        with pytest.raises(RuntimeError, match="synthetic post-DDL failure"):
            manager.upgrade()
    finally:
        event.remove(Engine, "after_cursor_execute", fail_after_table)
    assert_preserved(path, before)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0022_telnyx_http_identity",
        )
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='telnyx_ingress_rejections'"
            ).fetchall()
            == []
        )
    manager.upgrade()
    assert manager.is_current()
    assert_preserved(path, before)
```

## Independent follow-up — bounded admission and cancellation drain

Security/Reliability review identified additional queue/cancellation defects after
the first Standards pass. This reviewer inspected the resulting _run_work and
independently reran tests; attribution of original discovery belongs to that review.

Admission now uses fail_after with the remaining monotonic work budget before
reserving an execution slot. Once admitted, a separate asyncio task is shielded;
client cancellation drains that task to completion before releasing admission,
including repeated raw Task.cancel calls. It consumes the job failure while
propagating client cancellation, without returning an ACK or detaching SQL.

Own run of test_telnyx_asgi_durability.py plus test_telnyx_asgi_load.py:
**14passed,2warnings,8.07s**, exit0, evidence
`/tmp/ticket12/standards-queue-cancel/pytest.xml`. This includes primary's three
root regressions for bounded queue wait, delayed metrics and repeated cancellation.
Own additional independent probes: **2passed2.68s**, exit0, evidence
`/tmp/ticket12/standards-admission-refresh/pytest.xml`:

1. Occupy all8 admission tokens, call _run_work with a0.04s deadline. It raises the
   fixed capacity-deadline error in less than0.3s, performs no callable work and
   neither steals nor leaks borrowed tokens. All8 original tokens can be released.
2. Admit a worker blocked by Event, cancel its ASGI task10times, then allow the
   worker to complete with a RuntimeError. During every cancellation, task stays
   unfinished and admission remains held; final outcome is CancelledError, work
   completion is observed once, and admission/worker token counts return to0.

The former untimed-admission limitation is corrected and independently verified.
Filesystem fsync, server/transport backpressure and cancellation draining of already
running work remain nonpreemptible limits; no production latency SLA is inferred.
Ruff check passed in this follow-up; Markdown Python examples required formatter
normalization after report creation, corrected within this report only.

Follow-up probe source (run as a temporary module through the same offline runner):

```python
import asyncio
from threading import Event
from time import monotonic
import pytest
from test_telnyx_asgi import app as app
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.persistence import PersistenceUnavailable


def test_short_capacity_deadline_does_not_run_job(app):
    calls = []

    async def run():
        borrowers = [object() for _ in range(8)]
        for borrower in borrowers:
            await app._limiter.acquire_on_behalf_of(borrower)
        started = monotonic()
        try:
            with pytest.raises(PersistenceUnavailable, match="capacity deadline expired"):
                await app._run_work(
                    lambda: calls.append("forbidden"),
                    ExecutionDeadline.start(total_seconds=0.04, finalization_margin_seconds=0),
                )
            assert monotonic() - started < 0.3
            assert app._limiter.borrowed_tokens == 8
        finally:
            for borrower in borrowers:
                app._limiter.release_on_behalf_of(borrower)
        assert app._limiter.borrowed_tokens == 0

    asyncio.run(run())
    assert calls == []


def test_cancelled_worker_failure_is_drained_and_capacity_released(app):
    entered, release = Event(), Event()
    finished = []

    def work():
        entered.set()
        assert release.wait(2)
        finished.append(True)
        raise RuntimeError("synthetic job failure after client cancellation")

    async def run():
        task = asyncio.create_task(app._run_work(work, ExecutionDeadline.start()))
        try:
            while not entered.is_set():
                await asyncio.sleep(0.001)
            for _ in range(10):
                task.cancel()
                await asyncio.sleep(0.001)
                assert not task.done()
                assert app._limiter.borrowed_tokens == 1
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished == [True]
        assert app._limiter.borrowed_tokens == 0
        assert app._workers.borrowed_tokens == 0

    asyncio.run(run())
```

## Final CP5 source verification

At source/test candidate `d7b5d72a2e784ec954bf4f100eac9d4eaba7a1dc`, independently
queried origin and local HEAD (same SHA), found no source/test working diff, reread
final response/admission/cancellation code, and ran:

```bash
python scripts/check_telnyx_offline.py --python /tmp/ticket12/venv/bin/python \
  --output /tmp/ticket12/standards-cp5-final \
  tests/test_telnyx_asgi_durability.py tests/test_telnyx_asgi_egress.py \
  /tmp/ticket12/standards-probes/test_corrected.py \
  /tmp/ticket12/standards-probes/test_admission_refresh.py \
  /tmp/ticket12/standards-probes/test_migration23.py
```

Result: **38passed24.70s**, exit0. This includes all five independently authored
probes retained above and final durability/egress regressions. Source Ruff check
and diff check passed. Earlier focused96 and follow-up14 selections overlap;
counts must not be summed into a unique coverage claim. No complete pytest suite,
commercial endpoint, credential, activation or operational restore release was
executed by this reviewer. Final Standards opinion remains eligible OFFLINE for
direct orchestrator audit, PRODUCTION NO-GO, no newly confirmed P1/P2 pending in
this review's corrected candidate; AUD01 and external acceptance gates remain OPEN.

## Final framing follow-up and immutable candidate

Spec review identified a P3 protocol issue: an explicit Content-Length:0 on204
violated RFC9110§8.6. Standards independently agrees with the protocol classification;
no actual Telnyx rejection or commercial interoperability defect was reproduced.
Primary corrected the framing and added an absent-header/empty-body assertion.

Final immutable source/test candidate is
`533052f2d60ee43bd66e82170af1801f4523c76a`. Independently queried localHEAD and
origin branch (sameSHA), inspected the entire source/test delta fromCP5 (response
header conditional plus focused assertion only), and verified an empty working
source/test diff. Fresh offline run of test_telnyx_asgi.py plus
test_telnyx_asgi_durability.py: **22passed14.12s**, exit0, evidence
`/tmp/ticket12/standards-framing-final/pytest.xml`. Source/test Ruff check/format
and diff check passed. Earlier review counts remain valid for their named candidates
and are not represented as fresh full-suite executions. This report grants no CI
or real-provider assurance. Final Standards state is unchanged: no new confirmed
P1/P2 pending within this reviewed offline candidate; eligible for direct audit,
PRODUCTION NO-GO, AUD01 OPEN.

No new exception, accepted operational risk or issue checkbox closure is granted.
Direct orchestrator audit remains the next approval gate after completed delivery.
