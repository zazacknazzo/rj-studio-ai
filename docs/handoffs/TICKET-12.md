# Handoff — Telnyx Coexistence Ticket12

- Repository/origin: zazacknazzo/rj-studio-ai / https://github.com/zazacknazzo/rj-studio-ai.git
- Exact approved baseline: 246fe79a9bed4b202c49d3b2780320f6d5a0ca9c.
- Authorized branch: codex/telnyx-coexistence-12-composition only.
- Scope: offline ASGI ingress/readiness/quarantine tests, intercepted transport only.
  No real Telnyx/API/commercial credentials/activation/egress workers/production/main
  merge/Baileys/intelligence changes/Ticket13. Approval: issue11 comment7062936123.
- Exclusive writer: user explicitly confirmed this account in chat2026-11-21.
  Primary alone commits/pushes; independent reviewers may write separate reports.
  Human exclusivity required on every account transfer; Markdown is not a lock.
- Last remote SHA actually verified: CP5 d7b5d72a2e784ec954bf4f100eac9d4eaba7a1dc;
  Ticket12 branch absent before creation. Query origin for current SHA.

## Checkpoints

| CP | Completed / WIP / pending | Actual checks / failures | Remote SHA verified |
| --- | --- | --- | --- |
| CP0 | Spec/ADR/handoff first; code pending | baseline/origin/approval checked; 20 sender integration passed6.24s under IP guard; diff check | baseline above |
| CP1 | raw duplicate/smuggling checks and bounded byte streaming complete | 17passed0.19s; Ruff check/format PASS | CP0 above |
| CP2 | isolated ASGI auth/parse/SQLite/ACK; no runtime route | 27passed; initial1failed26passed due to FastAPI included-router introspection; test now inspects OpenAPI | CP1 above |
| CP3 | real-ASGI commit visibility, commit/SQL rollback, lock, fragmented/large body, lost ACK and expiry | 19passed; initial1failed18passed: SQL trace probe missed leading whitespace, corrected probe | CP2 above |
| CP4 | bounded durable rejection observations/0023, six readiness fields, metrics | 63passed15.15s including schema/history regressions; Ruff check/format | CP3 above |
| CP5 | strict HMAC/store quarantine, six restore snapshots, callbacks, load/concurrency, bounded admission and cancellation | corrected68passed19.93s; followup14passed7.39s; extra21passed8.74s; initial failures below | CP4 above |
| CP6–7 | Pending | Full suites/final review pending | None |

## Risks and limitations

AUD01 OPEN. Closed offline composition is not an operational antirollback system.
CX01/06/11/15/16/17/19/24/25/29/30/32/33/35/36/37 remain audit/production gates.
Public docs inspected, no Telnyx account calls; synthetic toolchain install separate
from app tests. Prior Ticket11 reports inspected, not claimed as current executions.
Fresh clone used --no-checkout (apparent initial deletions were unpopulated index/worktree,
not other-account WIP); switching to exact baseline populated it. No work discarded.
Toolchain installation in private /tmp/ticket12/venv; test guard reused from Ticket11.

## Exact next action

Fetch origin, verify branch/status/SHA and read this handoff. Reproduce:
`python scripts/check_telnyx_offline.py --python /tmp/ticket12/venv/bin/python tests/test_telnyx_sender_integration.py`
Then CP6: run full guarded pytest, independent reviews, lint/compile/pip/audit/Gitleaks; capture actual evidence, correct findings.
Account change must use its own isolated venv and record its actual check result.

## CP5 failures and review corrections (not hidden)

- Initial egress tests17failed22passed9.34s: incorrect test API/field names and missing
  fake-sender outcomes; fixed against actual contracts. Next1failed38passed11.70s:
  last request.body typo fixed to content; no production behavior relaxed.
- Initial0.05s writer wait load: unique99x204/29x503, duplicate122x204/6x503,
  0late successes; all204 assertion failed.0.5s wait next127x204/1x503 and128x204.
  Current test reports actual backpressure and requires identical-request retries
  after drain to recover every durable event exactly once. No claim of host SLA.
- Standards/Spec independently reproduced two P2 candidate defects: metrics could
  delay ACK after final check; direct constructor accepted unquarantined store.
  Fixed; same independent probes passed. Security reproduced unbounded capacity
  queue wait and rawasyncio cancellation detaching a running job; fixed with bounded
  admission and shield/drain retaining slots. Same independent probes passed.
- Last local load: unique125x204/3x503→3x204 retries; p95.13888s/p99.52874s;
  duplicate128x204 p95.06941s/p99.13383s; zero late successes. Synthetic only.
- Two pytest record_property/xunit2 warnings retained; JUnit properties exist.
- pip-audit first failed because default cache parent is read-only; rerun with explicit
  private cache completed, no known vulnerabilities returned. Not treated as initialPASS.
- Gitleaks8.30.1 archive checksum verified; tree3 raw baseline falsepositives
  (Ticket11 public schemahash, eval prose, synthetic operatorfixture), no ignores.

## CP6 framing correction

Spec independently flagged P3 RFC9110§8.6:204must omit Content-Length, including0.
Corrected helper and regression;10ASGItests passed. Both full runs on d7b5 were
interrupted intentionally to include this change, not reported as completedPASS.
Spec partial1730passed/1skip289.75s; local partial recorded in final evidence.
Next: publish correction/verify SHA, restart both guarded full suites on that SHA.
