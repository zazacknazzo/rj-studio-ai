# Ticket 07 — validation and independent audit

Delivery: 2026-11-11. Authorized scope: Ticket 07 only.
Base: `5b8f561250499ae2463688caf37d3876e7fa60a4` (Ticket 06).
Reviewed implementation: `ec51ffabd5ab701a42a0202ff70939dee6c985b0`.
Branch: `codex/telnyx-coexistence-07-ingress`.

## Result and comparison with Ticket 06

Ticket 06's authenticator remains byte-identical. Ticket 07 adds a dormant Message
adapter and an offline ingress interface returning empty 204 only after a successful
SQLite commit. It adds inbound provenance receipts to the existing transaction,
reuses the operational journal and human pause effects, and validates contradictory
Message/event/channel identities. There is no Telnyx route, runtime selection,
sender, lifecycle/status implementation, real connection or new intelligence.

| Telnyx payload | Canonical result | Durable effect |
| --- | --- | --- |
| message.received, body.type=text | InboundMessageReceived | Receipt, Message and processing admission; existing suppression gates apply |
| message.echo, outbound, origin=whatsapp_business_app | HumanMessageObserved | Journal and one logical pause effect; no Message/LLM input |
| message.received, body.type=edit | MessageEdited | Operational observation and opaque original reference; no historical mutation |
| message.received, body.type=revoke | MessageRevoked | Operational observation and opaque original reference; no historical mutation |
| Inbound media/location/attachments, unknown events, redundant whatsapp.messages | Rejected | No success ACK or partial batch |
| Delivery status / account lifecycle | Rejected by this Message adapter | Deferred to Tickets 08/09 |

Echo content can be text, media, empty or unknown; content never enters the canonical
human event. Authentication, identity and origin remain mandatory.

## Identity, time and transactions

`data.id` identifies the envelope, `payload.id` the logical Message, and
`body.foreign_id` an optional Meta alias. These never share an implicit namespace.
`original_message_id` remains in `telnyx_original_opaque` regardless of string shape;
it is not a historical Message lookup. Phone-hidden Customers use `bsuid:` and
explicit `from_user_id` provenance, even when the opaque ID looks like a phone.
Missing optional sender phone fields are supported; malformed explicit senders fail.

The unique inbound event scope index and BEGIN IMMEDIATE serialize duplicates.
Distinct envelopes may share a logical Message, but cannot create a second inbound.
Minimal receipts survive raw content purge, preventing replay re-admission. Shared
aliases never merge Customers or suppress a distinct logical human Message. A known
human Message cannot repause after resume; a new delayed human Message does.

Source time is only syntactically valid Unix seconds from body.timestamp, with
source <= envelope event time. This immutable evidence stays identical on replay as
the local clock advances. Admission after resume additionally requires:
`cutoff < source <= event <= local receipt`. Missing, old or contradictory evidence
is terminal suppressed, including replay after clock correction. Local receipt,
signature timestamp and event time never replace source time. Meta/Twilio continue
to lack source provenance after resume; their existing limitation is unchanged.

The entire local batch (separately signed envelopes) validates before persistence;
all receipts, Messages, pause effects and fencing commit together. A failure in any
statement or commit rolls back everything. The tuple is a local seam, not a Telnyx
HTTP batch claim. Monotonic budget checks bound parsing, lock waiting and SQL work,
with precommit and postcommit checks. A commit completing after expiry receives no
success ACK; replay is safe. Filesystem fsync is not preemptible, so there is no hard
real-time latency guarantee. No LLM or external send occurs in this transaction.

## Validation

Final complete suite: **1593 passed, 1 historical skip**, 136.23 seconds.
Independent Spec reviewer complete suite: **1593 passed, 1 historical skip**, 128.22
seconds. Both ran implementation ec51ffa with zero errors/failures. Focused corrected
suite: **111 passed**, independently repeated by Standards. Ruff check,
Ruff format check (274 Python files), compilation, dependency consistency and diff
checks passed. All runs used a sanitized environment, synthetic keys/data and real
temporary file-backed SQLite. A Python audit hook blocks IP connect/sendto, including
child Python processes. No commercial .env or real customer database was used.

The one historical skipped test is `test_historical_v8_record_remains_loadable` in
`test_commercial_steering.py`; its local history fixture is not committed. No Telnyx,
authentication, pause or compatibility case is skipped.

| Required coverage | Evidence in tests/test_telnyx_messages.py unless noted |
| --- | --- |
| 1–3. Official-shape synthetic payloads, text, human echo | signed_classification_and_durable_ack |
| 4. Wrong echo origin | wrong_echo_origin_rejected |
| 5. Echo never generates | echo_content_never_becomes_input, signed_classification_and_durable_ack |
| 6. Edit/revoke never generate | signed_classification_and_durable_ack, original_reference_is_always_opaque_and_never_changes_history |
| 7–9. Event/Message/Meta identities, repeat envelopes | signed_classification_and_durable_ack, lost_ack_restart_and_repeated_envelopes |
| 10. Ambiguous original_message_id | original_reference_is_always_opaque_and_never_changes_history |
| 11–12. Duplicates, delayed/out-of-order echo, resume | concurrent_duplicate_requests, new_inbound_eligible_and_late_echo_repauses |
| 13–14. New eligible versus old/unproven source | new_inbound_eligible_and_late_echo_repauses, old_or_unproven_inbound_suppressed_after_resume, contradictory_or_future_event_time_does_not_bypass_resume |
| 15–16. Mixed rollback, SQLite statement/commit failure | mixed_batch_rolls_back_every_effect_before_ack |
| 17. Lost ACK and replay | lost_ack_restart_and_repeated_envelopes, future_event_replay_retains_provenance_after_clock_catches_up |
| 18. Echo versus generation | concurrent_echo_fences_generation_and_submission, echo_during_llm_discards_result_without_holding_sqlite |
| 19. Echo versus send authorization | concurrent_echo_fences_generation_and_submission, both writer orders |
| 20. Wrong/ambiguous channel | channel_change_rejected_even_without_pause_control, unresolved_echo_cannot_ack_or_apply_to_ambiguous_conversation, conflicting_identity_is_not_silently_deduplicated |
| 21. Malformed JSON/unsupported content | invalid_or_unsupported_payload_never_acks, malformed_json_and_unsigned_requests_have_no_effect |
| 22. Unauthenticated ingress | malformed_json_and_unsigned_requests_have_no_effect; Ticket 06 authentication suite |
| 23. Meta/Twilio preservation | Entire legacy provider, ingress, generation, delivery and policy suites; adapters unchanged |
| 24. Privacy | no_private_content_or_credentials_in_errors_or_journal; SQLite error traceback sentinel; Ticket 06 redaction suite |
| 25. Restart/idempotence | lost_ack_restart_and_repeated_envelopes, purged_inbound_cannot_be_readmitted_by_replay |
| Deadline, schema and migration | ingress_deadline_never_returns_late_success, missing_inbound_receipt_index_fails_readiness, upgrade_preserves_previous_journal_and_rolls_back_atomically |
| Hidden-phone identity regressions | paired_hidden_phone_inbound_and_echo_share_one_pause, hidden_phone_accepts_absent_optional_phone_field, explicit_malformed_sender_is_rejected_with_opaque_identity |

Generation/send concurrency uses separate connections and deterministic threading
barriers. Commit failure uses a deferred real foreign-key violation. Another
connection reads committed data from inside the ACK spy. These are not mock-only
persistence tests. The fake sender records no calls; ingress has no sender dependency.

## Standards review

Initial independent review found one P2: phone-shaped BSUID was parsed as E.164 on
its echo, splitting the Conversation and pausing the wrong identity. Correction:
explicit opaque provenance precedes phone shape, with consistent address checks.
The reviewer independently reran the corrected 111 cases, inspected the complete
baseline diff and cleared ec51ffa: **no remaining P1/P2 or actionable smells**.

## Spec review

Initial independent review found two P2s. Receipt-relative canonical timestamp
validation changed the same event on replay after clock correction; the fix keeps
canonical source evidence immutable and checks local time at admission. Optional
phone absence was incorrectly rejected despite explicit BSUID evidence; guarded
sender extraction now accepts absence but rejects malformed explicit values.
Eleven new regression cases cover these findings and the Standards correction.
The final Spec reviewer independently ran the entire suite (1593 passed, one
historical skip), inspected the complete baseline diff and cleared ec51ffa:
**no remaining P1/P2, missing requirements or scope expansion**.

## Privacy and preservation

Gitleaks scanned both implementation commits with full redaction: **no leaks**,
without ignores or scanner exceptions. Only synthetic public test data is committed;
no key, database, raw provider payload archive, commercial .env or customer content.
The prior Baileys worktree's HEAD, working-tree status and all 272 tracked-file hashes
are unchanged. Local main is unchanged; remote main remains
`af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`. Ticket 06 remote remains the approved base.
Provider factories, main.py, configuration, domain values, Meta/Twilio, generation,
grounding, persona and frozen intelligence retain the approved implementation.

## Residual risks and next-ticket gate

No issue #11 checkbox is closed without the orchestrator's direct audit/approval.

- CX-01: inbound receipts join the existing unbounded retention hold; Ticket 13 must
  implement erasure/retention with replay protection before pilot.
- CX-02/CX-03: signed echo pause/deduplication/delay tested offline; runbook now says
  pause before manual activity and inspect in_flight_possible. Echo completeness and
  usable operator workflow still require Tickets 12–13.
- CX-04/CX-05: source/cutoff, skew and clock-correction replay covered offline; real
  timestamps/NTP and deployment validation remain open. Meta/Twilio limitation persists.
- CX-12/CX-13: duplicate profile envelopes, rejected redundant route, exact channel,
  separate aliases and opaque identities covered. Live subscriptions and explicit
  phone/BSUID/provider migration remain open; no automatic identity merge is added.
- CX-14: edit/revoke observation implemented; delivery statuses remain Ticket 08.
- CX-19: independent full-suite evidence complements local validation; no CI or
  orchestrator sign-off is inferred. The historical skip is explicit.
- CX-24: offline durability-before-ACK is covered. Raw ASGI duplicate headers and
  streaming/body limits remain Ticket 12; no route was enabled.
- New CX-29: unsupported formats fail closed and may trigger provider retries. Before
  external ingress, Tickets 12–13 need approved durable handling/visibility and tests
  without silent 2xx, fabricated input or retry storms. Status/lifecycle first require
  their respective Tickets 08/09. This is a composition blocker, not permission to
  implement those tickets now.

All other risks remain open; newly added CX-26–CX-28 product/SaaS/model-routing
records are preserved and are outside Ticket 07. No exception or risk acceptance
was silently granted. Real operation, sending, onboarding and main merge remain
unauthorized. The technical seams are available for Ticket 08, but work starts only
after the user's direct GitHub audit and explicit approval.

## Changed files

- `providers/telnyx_messages.py`: authenticated Message adapter.
- `webhook_ingress.py`: offline parse/transaction/ACK boundary.
- `inbound_events.py`: provenance receipts and exact identity validation.
- `persistence.py`: optional strict provenance and deadline checks in existing transaction.
- `migrations/versions/0018_inbound_event_receipts.py` and `migrations/__init__.py`:
  side table/indexes and schema verification.
- `tests/test_telnyx_messages.py`: 111 offline cases including review regressions.
- `tests/test_migrations.py`, `tests/test_agentic_intake_migration.py`,
  `tests/test_openai_metadata_migration.py`: expected migration head only.
- `docs/specs/V1-telnyx-coexistence-ticket-07.md`, `docs/specs/README.md`,
  `docs/decisions/0015-durable-telnyx-message-ingress.md`,
  `docs/automation-operations.md` and this validation record.

Source modules above are under `src/rj_studio_ai/`. No dependencies changed.
