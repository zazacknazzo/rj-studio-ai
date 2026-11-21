# Handoff — Telnyx Coexistence Ticket 11

- Repository/origin: zazacknazzo/rj-studio-ai / https://github.com/zazacknazzo/rj-studio-ai.git
- Exact approved T10 baseline: `07c1b7dc150d7eb1776b97d891cd29347adffd37`.
- Branch: `codex/telnyx-coexistence-11-sender`; absent remotely at initialization.
- Audit read directly through GitHub at `502bca89e64b45e981ad9c5f2eeb189aad3dd9e6`;
  audit branch is documentation and must NOT be merged.
- Authorized: offline text sender, intercepted transport, SQLite/tests/docs/checkpoints,
  normal push of this branch and evidence on issue #11. No runtime wiring, commercial
  credentials, external Telnyx requests, activation, public route, main merge or T12–13.
- Writer: primary implementing account in this session. Another account must arrange
  human-exclusive control before writing; this file cannot coordinate distributed locks.
- Current SHA: query origin. Last remote SHA before initial checkpoint: baseline above.

## Checkpoints

| CP | State | Validation / next work |
| --- | --- | --- |
| CP0 | Continuity, spec and ADR written before functional implementation | Docs inspected; git diff --check. No tests run yet. |
| CP1 | Pending | Deterministic request + durable integrity identity |
| CP2 | Pending | Injected transport + strict responses/errors |
| CP3 | Pending | Runner + SQLite atomic gates |
| CP4 | Pending | Adversarial concurrency/crash/restore tests |
| CP5 | Pending | Corrected toolchain, full suite/checks, independent reviews |
| CP6 | Pending | Final report + issue evidence + remote verification |

## Risks

AUD-01 remains OPEN: consistent old SQLite can lose submission/disconnect/consent fences.
T11 specifies quarantine and demonstrates the limitation; no operational recovery is
implemented. AUD-02 requires isolated updated pip/pytest and private temp0700 before tests.
AUD-03 protocol now written; rehearsal pending, real second-account control unproven.
CX-01/06/11/15/16/17/19/24/29/30/32/33/35/36/37 remain open until audit/operational gates.
Historical v8 fixture skip must be reported. Offline tests never prove WhatsApp delivery.

## Exact next action

After verifying CP0 remotely, inspect `src/rj_studio_ai/providers/base.py`, `delivery.py`,
`telnyx_submission.py`, authorization/finalization in `persistence.py`, migration0021,
and `tests/test_telnyx_submission.py`; implement CP1 per ADR0019. Create isolated
venv in private `/tmp/ticket11` and resolve corrected pip/pytest from PyPI before testing.
Read current origin/status/handoff first on any account change. No sender code yet.
