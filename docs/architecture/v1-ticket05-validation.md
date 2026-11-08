# Ticket 05 validation and independent review

Base: `1901a364123c38dc0e1d36a8ea9706b035eef420` on remote
`codex/telnyx-coexistence-04-outbound`. Local Ticket 04 branch has the
`-outbound-fencing` suffix but the same SHA and clean tree.

Work uses a new isolated branch `codex/telnyx-coexistence-05-admin`. The unpublished
local implementation `965ee85bc265631354fbf9cb750ae5cd4c18aaa9` was inspected and
explicitly reused as `701dfa6`, without changing its original worktree. New fixes
were developed with failing regressions first; this report does not claim the
reused implementation was freshly authored in this execution.

## Observable acceptance matrix

Tests below are in `tests/test_automation_operations.py` unless otherwise stated.
All database effects use real temporary SQLite; senders and LLMs remain synthetic.

| Request | Observable proof |
| --- | --- |
| 01 authenticated query | `test_authenticated_query_is_private_and_read_only`; complete database dump unchanged |
| 02 anonymous rejection | Same test; HTTP 401 with Bearer challenge |
| 03 invalid credential | `test_wrong_credentials_cannot_inspect_or_mutate` |
| 04 unauthorized operator/resource | `test_fail_closed_configuration_and_authorization`, `test_resource_scope_and_other_conversation_are_independent` |
| 05 absent/invalid configuration | `test_fail_closed_configuration_and_authorization`, `test_configuration_repr_dump_and_errors_hide_digest` |
| 06 idempotent pause | `test_pause_resume_are_durable_cas_and_idempotent`, `test_api_commands_receipts_conflicts_and_redaction` |
| 07 pause during generation | `test_manual_pause_during_llm_invalidates_result_without_database_lock` |
| 08 pause during outbound authorization | `test_manual_pause_races_delivery_authorization_in_both_orders` |
| 09 resume after restart | `test_migration_preserves_ticket04_evidence_and_rolls_back_atomically`, `test_pause_resume_are_durable_cas_and_idempotent` |
| 10 correct revision | `test_pause_resume_are_durable_cas_and_idempotent` |
| 11 stale revision | `test_api_commands_receipts_conflicts_and_redaction` |
| 12 concurrent resumes | `test_concurrent_commands_have_single_cas_winner` |
| 13 pause versus resume | `test_resume_and_human_intervention_serialize_in_both_orders` |
| 14 independent Conversations | `test_resource_scope_and_other_conversation_are_independent` |
| 15 active handoff preserved | `test_handoff_and_unknown_are_not_released`; existing release tests remain in full suite |
| 16 suppressed/cancelled backlog | `test_pause_fences_generation_and_resume_only_allows_new_inbound`, `test_manual_pause_fences_claimed_outbound_and_preserves_possible_submission` |
| 17 unknown preserved | `test_handoff_and_unknown_are_not_released`; `test_outbound_pause.py::test_restart_at_submission_boundaries_never_replays` |
| 18 duplicate echo | `test_echo_resolution_after_resume_is_conservative` duplicate and other-envelope cases |
| 19 delayed echo | Same test, old-timestamp case; receipt/revision persist |
| 20 new echo | Same test, new case; both commit orders in `test_resume_and_human_intervention_serialize_in_both_orders` |
| 21 ambiguous ordering | Same test, ambiguous-alias case; `test_resume_suppresses_ambiguous_or_delayed_inbound` |
| 22 credential/PII exclusion | Query allowlist, redaction and invalid-command tests; no content/external IDs/tokens returned |
| 23 Meta/Twilio compatibility | `test_legacy_messages_keep_unresumed_behavior_but_require_source_time_after_resume` and existing provider/runtime suites |
| 24 transactional rollback | `test_operation_receipt_failure_rolls_back_pause_and_cancellation`; migration fault injection |
| 25 crash/restart recovery | `test_resume_recovers_after_process_crash_or_lost_response`; child uses abrupt exit before/after commit, exact key replay |

Additional regression: `test_resume_cutoff_never_moves_backwards_after_clock_regression`
first demonstrated unsafe admission, then passed with monotonic local boundaries.
Both operator-only and interleaved-echo variants are covered. Timestamps never order
echo identity or replace operational revision CAS.

## Known limits

Meta/Twilio constructors and unresumed behavior remain unchanged. Their current
adapters provide no trustworthy Message source time, so their inbounds after resume
are conservatively suppressed. This is not a usable live resume for those adapters;
do not present clearing operational pause as proof that all eligibility gates pass.
Adapter provenance work is outside Ticket 05. No real Telnyx integration or eligibility
has been validated. No frontend, CRM or later ticket is implemented.

Echo remains best-effort. Previously unseen delayed human activity repauses; known
logical duplicates do not. A request authorized before pause can cross HTTP later.
Journal/control/receipt retention remains unbounded. Production and pilot remain
blocked, and Ticket 06 needs separate authorization.

## Final validation — 2026-11-08

Implementation reviewed: `fe8de5e6dbe527512f82fe754a51200bfbbac905`.
The final documentation commit changes no runtime or test behavior.

- Full pytest suite: **1368 passed, 1 skipped**, 67.26 seconds. The existing skip is
  `test_historical_v8_record_remains_loadable`, whose local historical evidence is
  not checked into Git. No operational or provider test was skipped.
- `ruff check .`, `ruff format --check .` (261 files), `compileall -q src tests`
  and `git diff --check`: passed.
- Environment sanitized, commercial `.env` absent from this isolated worktree,
  pytest plugin auto-loading disabled, Python audit hook blocks IPv4/IPv6 socket
  connect/sendto, including child processes. No live sender, onboarding or paid call.
- Matrix includes migration rollback, real SQLite concurrency and process crash
  recovery. No temporary database, validation XML or machine metadata is committed.

## Independent Standards review

A separate reviewer read the full base-to-implementation diff, AGENTS, local
standards, architecture and relevant ADRs. **0 findings; no pending P1/P2.**
Confirmed separate authentication and resource authorization, atomic controls and
receipts, lateral migration, retained handoff/unknown/submission evidence, monotonic
cutoff including interleaved echo, and unchanged intelligence. Independently ran
**61 operational tests**, all passing offline; diff check passed.

## Independent Spec review

The initial independent review found **1 P2**: a backwards wall clock could lower
the resume cutoff and admit old inbound work. A failing regression reproduced it;
the correction preserves local temporal boundaries in operator and echo paths.
The final independent reviewer read the actual diff and confirmed the fix plus
both writer orders and subprocess crash/replay coverage. **0 pending P1/P2.**
Independently ran **162 operations/generation/outbound tests**, all passing offline.
The documented Meta/Twilio limitation remains; no live resumption is claimed.

## Publication audit

Reviewed each new commit and its changed file versions. Only Python and Markdown
files are introduced/changed; no `.env`, private keys, session, database, binary,
commercial credential or real customer record is included. Pattern scanning and
manual diff review found no new credential/PII exposure. Phone-pattern matches in
the existing migration test file are unchanged baseline synthetic fixtures, not
new data. Synthetic operator test secrets are explicitly test-only.

Frozen providers, prompts/persona, grounding, handoff policy, business knowledge,
generation/application behavior and evaluation code match the approved base.
Baileys HEAD, status and all 272 tracked-file hashes match the pre-work snapshot.
Only the isolated Ticket 05 branch is to be pushed normally, without force or merge.
