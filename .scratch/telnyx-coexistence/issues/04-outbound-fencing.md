# 04 — Safe cancellation and outbound authorization

Status: done

Base: 2417708e37bb633c6af3d0ec732b64baa61e629f.
Spec: docs/specs/V1-telnyx-coexistence-ticket-04.md.
Dependencies: Tickets 01–03 independently reviewed PASS.
Acceptance: transactional pause/cancellation, claim+submission fences, preserved
irreversible evidence, callbacks/ordering/handoff compatibility, all specified
race/restart/privacy tests, full checks and independent Standards/Spec review.

## Comments

- Ticket 04 explicitly authorized. Isolated worktree; Baileys preserved.
  No Ticket 05, external APIs, credentials, live sending, push or merge.

- Implementation: migration 0016 cancels eligible outbox rows in the pause
  transaction and protects later ready transitions. Claim, normal submission and
  legacy reply authorization exclude paused Conversations. Possible-submission
  evidence and completed attempts remain intact; no I/O holds a DB transaction.
- Independent Spec review found one P2: final-attempt retry exhaustion bypassed
  pause cancellation. Fixed in da35f14 with explicit neutral retry exhaustion
  input resolved against pause inside finalization. Added five regressions for
  final attempts, both commit orders, and unknown validation. Reinspection PASS.
- Independent Standards PASS, including correction reinspection and 61 focused
  tests. Spec PASS, including correction reinspection and 177 affected tests.
- Full final suite: 1307 passed, 1 pre-existing skip (local historical evidence
  absent from Git), 74.60 seconds. 61 new outbound-pause cases. Ruff check and
  format check passed (252 files); 139 src/tests Python files compile without
  writing bytecode; diff check passed. No line-coverage percentage measured.
- Tests used synthetic data, temporary SQLite, fake senders and an IP-network
  denial guard. No commercial environment, credentials, live provider, credits,
  WhatsApp, push, merge or Baileys change.
- Marker-to-HTTP race remains explicit: already-authorized work can escape pause.
  Unknown has no automatic resend; acceptance and callbacks remain evidence.
  Journal/control retention without purge remains a release blocker.
- Technically ready for orchestrator review and possible Ticket 05 authorization.
  Ticket 05 is not started; authenticated human operation and production release
  remain unavailable.
