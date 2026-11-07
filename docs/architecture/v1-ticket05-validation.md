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
