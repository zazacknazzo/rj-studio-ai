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
- Last remote SHA actually verified: CP3 c1bc518e5f56aed28f23b0903e941a602030dcd5;
  Ticket12 branch absent before creation. Query origin for current SHA.

## Checkpoints

| CP | Completed / WIP / pending | Actual checks / failures | Remote SHA verified |
| --- | --- | --- | --- |
| CP0 | Spec/ADR/handoff first; code pending | baseline/origin/approval checked; 20 sender integration passed6.24s under IP guard; diff check | baseline above |
| CP1 | raw duplicate/smuggling checks and bounded byte streaming complete | 17passed0.19s; Ruff check/format PASS | CP0 above |
| CP2 | isolated ASGI auth/parse/SQLite/ACK; no runtime route | 27passed; initial1failed26passed due to FastAPI included-router introspection; test now inspects OpenAPI | CP1 above |
| CP3 | real-ASGI commit visibility, commit/SQL rollback, lock, fragmented/large body, lost ACK and expiry | 19passed; initial1failed18passed: SQL trace probe missed leading whitespace, corrected probe | CP2 above |
| CP4 | bounded durable rejection observations/0023, six readiness fields, metrics | 63passed15.15s including schema/history regressions; Ruff check/format | CP3 above |
| CP5–7 | Pending | Not executed | None |

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
Then CP5: strict Telnyx request binding, restore quarantine, callback/consent/concurrency/load evidence.
Account change must use its own isolated venv and record its actual check result.
