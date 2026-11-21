# Ticket 11 — independent Spec Review

Date: 2026-11-21, America/Sao_Paulo. Reviewer: separate Spec Review agent;
primary implementer retains exclusive Git writing. Reviewed baseline:
`07c1b7dc150d7eb1776b97d891cd29347adffd37`. This review used direct source, specification,
official OpenAPI and executable probes, not an implementer validation report.
Final tested candidate: `789c2c89328b0472506c3d34593dfe741c052883`, confirmed directly
with git rev-parse HEAD. Production source remains identical to `a049753205001d81a9ac0f11253eab5760a2f017`.
**Independent integral: 2130 passed, 1 skipped in 399.84s, exit 0. PASS for the authorized
offline scope, with no new P1/P2 pending after the corrections below. Operational NO-GO.**

## Direct inspection

Read AGENTS.md, Ticket 11 spec, ADR0019, ADR0018, actual baseline diff, request signer,
concrete sender, runner, authorization/finalization, submission gates, migration0022
and its schema readiness inspection, request/response/integration/adversarial/migration
tests. Verified no diff in inspected Meta/Twilio providers, runtime main/settings,
generation/application intelligence paths.

Independently decoded `/tmp/ticket11/openapi` and followed:
`paths./messages/whatsapp.post`, `messaging_WhatsappMessage`,
`messaging_WhatsappMessageContent`, `WhatsappResponse`, `RCSToItem`.
SHA256 independently recomputed:
`fc59cb60a25c5091e73889842c808f1db7b4c0bb36bbb0228ee9ed2f629eca18`.
Also read the official idempotency Markdown snapshot. These are public documentation
snapshots, not observations of a commercial account or API operation.

| Requirement | Direct evidence and limits |
| --- | --- |
| Official WhatsApp request | Fixed POST/HTTPS/api.telnyx.com/v2/messages/whatsapp; text under whatsapp_message, explicit WHATSAPP and profile; no SMS or Graph fallback. |
| Exact identity | Canonical UTF8 sorted compact JSON, empty query and header UUIDv4; keyed MAC covers organization/profile/channel/recipient/method/scheme/host/path/query/modality/key/body bytes. No extra plaintext body or public predictable-content digest. |
| Durable gates | Existing assessment remains inside BEGIN IMMEDIATE; request binding additionally checks actual eligible lifecycle organization/profile/channel before the same transaction commits delivery/attempt/first markers. |
| I/O ordering | Runner prepares first, authorizes/commits next and invokes one injected exchange last; callback/response finalization uses the existing scoped T08 ledger. No SQLite transaction crosses exchange. |
| No hidden retry | No Telnyx SDK or default client exists. Exchange receives retries=0, redirects=false and explicit connect/read budgets. Trusted injected callables are not a sandbox; operational transport remains a future gate. |
| Acceptance | Official 200 response identity/text must match; incomplete/malformed/unknown status denies acceptance. sent/delivered/read in HTTP response never advance T08 delivery evidence. |
| Ambiguity | 409/10036,422/10027 have distinct fixed unknown reasons; other409/422/429/5xx/redirects/timeouts/lost responses never authorize retry or a new key. |
| Local non-submission | Preparation before authorization/exchange can create attempt-scoped NOT_SUBMITTED evidence, with bounded retry and the original logical key. |
| Recovery | Old-snapshot tests explicitly reproduce AUD-01. No field/MAC inside restored SQLite is claimed as freshness proof. External quarantine/reconciliation remains specified, unimplemented and operationally blocking. |
| Scope | No activation/public route/runtime selection/commercial credentials/T12–13 implementation or intelligence change found in inspected diff. |

## Findings and independently verified corrections

- **SPEC11-01, P2, request-schema divergence.** OpenAPI declares
  `messaging_profile_id` with format UUID; initial signer accepted arbitrary tokens
  and request fixtures used `synthetic-profile`. Direct construction confirmed an
  invalid profile produced a request. Implementer corrected signer and canonical
  validation to require canonical UUID and replaced the shared synthetic fixture with
  a valid synthetic UUID. My direct probe then confirmed non-UUID profile fails
  locally before request construction. No production account was involved.
- **SPEC11-02, P2, malformed success could become acceptance.** A valid synthetic
  acceptance with `from.status='future_status'`, `from.line_type='FutureLine'`,
  `wait_seconds='NOT_A_NUMBER'` or `received_at='NOT_A_DATETIME'` was accepted in four
  separate direct probes, although these present known fields violate the official
  schema. Implementer added validation of present known fields and contradictory
  known body modalities. I reran all four original probes against corrected source:
  each raised the fixed `telnyx_response_invalid`; no exchange repetition occurred.
  Unknown additional fields remain forward compatible.
- **SPEC11-03, test compatibility.** My own `pytest -x` reproduced the historical
  migration test's hardcoded head 0021 mismatch after adding 0022:
  1 failed/33 passed in 34.24s. An initial independent integral run also found the
  historical downgrade test expects the phrase `backup/restore`; new 0022 originally
  used different wording. These are test/contract compatibility corrections, not
  loss of historical data or authorization bypasses. Both were corrected without
  weakening historical preservation assertions. A completed independent integral
  run later found the same obsolete-head expectation in
  `test_telnyx_messages.py::test_upgrade_preserves_previous_journal_and_rolls_back_atomically[False]`.
  That sole remaining latest-head assertion was changed 0021→0022; I inspected the
  one-line diff and confirmed rollback/effects/FK assertions were unchanged.
  A global search found the only remaining 0021 references are intentional historical
  setup/checks in `test_telnyx_http_migration.py`. Final verification follows.
- **SPEC11-04, P2, default concrete sender could consume legacy work.** My own SQLite
  probe created a pending Meta delivery and constructed the public runner with its
  default provider=None plus a concrete Telnyx sender. Three run_once calls produced
  Meta retryable/attempt1, retryable/attempt2 and failed/attempt3 without exchange.
  The provider mismatch was detected after claiming and incorrectly counted as a
  local preparation failure for that legacy delivery. Implementer now normalizes the
  concrete sender's default provider to telnyx and rejects incompatible explicit
  providers in both runner/executor construction before a claim. I reran my original
  probe for both Meta and Twilio: rows remained pending/attempt0, default executor
  scoped to telnyx, and explicit meta/twilio configurations raised ValueError in both
  constructors. The final diff contains permanent regressions for both providers.

## Execution evidence

Own environment inspection: Python 3.12.14, SQLite 3.53.1, pip 26.3, pytest 9.2.0.
`/tmp/ticket11/run -m pip check`: no broken requirements. Read and verified the wrapper:
`env -i`, no inherited commercial credentials/proxies, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1,
private `/tmp/ticket11` parent 0700, explicit separate --basetemp, and Python socket guard
for AF_INET/AF_INET6 inherited through PYTHONPATH. Guard is a Python-level control,
not a claim of kernel isolation or containment of arbitrary native executables.

Initial full command:

```bash
/tmp/ticket11/run -m pytest --basetemp=/tmp/ticket11/tmp/spec-full -ra \
  --junitxml=/tmp/ticket11/spec-full.xml > /tmp/ticket11/spec-full.log 2>&1
```

That obsolete pre-correction run was explicitly interrupted after independent
failure collection because it had collected old candidate functions. Actual partial
result: **2 failed, 942 passed, 1 skipped in 287.89s**, exit 130. Both failures were
SPEC11-03 above. It is not reported as a completed or passing integral run. A direct
`-x` reproduction used its own separate basetemp and is counted separately, not summed.
An intermediate run after schema/profile fixes was also interrupted after reaching
an already-known downgrade wording mismatch: **1 failed, 426 passed, 1 skipped in 119.01s**.
A third partial run after that correction was interrupted when SPEC11-04 was reproduced
and corrected: **647 passed, 1 skipped in 175.24s**, with no failures before interruption.
These are incomplete executions, not passing full suites. Full commands used separate
private basetemp directories `spec-final` and `spec-verified`; counts are not summed.

Completed integral before the last historical-head correction:

```bash
/tmp/ticket11/run -m pytest --basetemp=/tmp/ticket11/tmp/spec-approved-candidate -ra \
  --junitxml=/tmp/ticket11/spec-approved-candidate.xml \
  > /tmp/ticket11/spec-approved-candidate.log 2>&1
```

That integral execution completed with **1 failed, 2129 passed, 1 skipped in 402.26s**,
exit 1. The sole failure was the remaining historical journal migration head assertion
reported above, not sender behavior. It was retained as failed evidence, not hidden.
After that one-line test compatibility correction I independently reexecuted both
parametrizations of the exact failed migration test, then started the final integral:

```bash
/tmp/ticket11/run -m pytest \
  'tests/test_telnyx_messages.py::test_upgrade_preserves_previous_journal_and_rolls_back_atomically' \
  --basetemp=/tmp/ticket11/tmp/spec-historical-head -ra
/tmp/ticket11/run -m pytest --basetemp=/tmp/ticket11/tmp/spec-final-green -ra \
  --junitxml=/tmp/ticket11/spec-final-green.xml > /tmp/ticket11/spec-final-green.log 2>&1
```

Exact focused migration reproduction: **2 passed, 0 skipped in 3.55s**.
Final independent integral: **2130 passed, 1 skipped in 399.84s, exit 0**, tested candidate
`789c2c89328b0472506c3d34593dfe741c052883`. XML independently inspected: 2131 cases,
0 failures, 0 errors, 1 skip. The sole skip is
`tests/test_commercial_steering.py::test_historical_v8_record_remains_loadable`:
"Local history evidence is not checked into Git" (line 430). No fixture was invented.
No production code changed since source candidate `a049753205001d81a9ac0f11253eab5760a2f017`;
only the historical test's expected current migration head changed before this green run.
The full suite includes the permanent regressions for all three reproduced P2 findings.

Raw temporary evidence is not the continuity source; commands and findings are durable
here. To reproduce with the committed equivalent sanitized runner in a fresh isolated
venv, use `python3 scripts/check_telnyx_offline.py --python /path/to/venv/bin/python`.
This reviewer inspected that script; the actual executed commands are shown above.


## Limits and disposition

Executed: own probes, own dependency/environment checks and actual pytest processes.
Inspected: source/spec/OpenAPI/gates/migration/transport policy. Simulated: provider
responses, callbacks, crashes/restores in the offline suite. Unproven/not executed:
real Telnyx calls, credentials, account eligibility, external idempotency retention,
real timeout enforcement, actual delivery, operational restore quarantine, production,
a second independent human account's write-control handoff and kernel-level isolation.
AUD-01 remains open. New receipt retention remains subject to CX-01; CX-06 residual
marker→HTTP window and channel activation/consent/composition gates remain open.
**Offline disposition: PASS within the authorized Ticket 11 offline scope.** The three
new reproduced P2 findings are corrected and independently rechecked, and the final
independent full suite passes with the single explicitly disclosed historical skip.
No new P1/P2 remains pending in this implemented scope.

**Operational/production disposition: NO-GO.** AUD-01 has no effective operational
quarantine/freshness mitigation; real account/transport/composition, consent, retention
and release gates remain open. This review grants no operational authorization,
closes no issue11 checkbox and does not replace direct orchestrator audit.

## Final evidence integrity

| Temporary artifact | SHA256 |
| --- | --- |
| spec-final-green.log | `eb023dfddd9f8ca1050da1b2f8b82903bb3bbf9905822ca39eda486081a3784d` |
| spec-final-green.xml | `8cc54095db7f9dbdc2474d30c97e694f8a3fa2778b5080969715afcc896eea5a` |
