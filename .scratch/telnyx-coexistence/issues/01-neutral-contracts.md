# 01 — Neutral contracts and classification

Status: done

Approved scope: [Ticket 01 spec](../../../docs/specs/V1-telnyx-coexistence-ticket-01.md).
Base: `7495fb8e47482a2cba2958ef4bf4e6a210b6c018`.

## Acceptance

- Distinct Customer input, human activity, delivery status, lifecycle, edit and revocation.
- Separate event ID, Message ID, original target and namespaced aliases.
- No manual/change event becomes Customer input or generates an AI Reply.
- Acceptance remains distinct from confirmed delivery; ownership tokens are not authentication.
- Meta/Twilio and legacy constructors remain compatible.
- Document future stable submission keys without implementing persistence or a sender.
- New/relevant existing tests and static checks pass, with no external APIs or customer data.

## Comments

- 2026-10-31: Owner conditionally authorized only this ticket, explicitly adding
  edit/revoke separation. Created isolated worktree from approved baseline;
  experimental Baileys worktree is excluded. Ticket 02 has not started.
- 2026-10-31: Implemented contracts and explicit classification only. Full offline
  suite: 1172 passed / 1 historical-fixture skip; 54 new cases. Ruff check/format,
  compileall and diff checks passed. Ready for orchestrator review; no approval
  for the next ticket is implied by this implementation status.
