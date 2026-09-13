# Domain Docs

This repository uses a single domain context.

## Before exploring

- Read `CONTEXT.md` at the repository root.
- Read records under `docs/adr/` that affect the area being changed.
- Proceed silently if either location does not yet exist.

## Consumer rules

- Use the glossary's canonical terms in code, tests, tickets, and documentation.
- If a requested change conflicts with an ADR, surface the conflict instead of silently overriding it.
- Keep `CONTEXT.md` limited to domain vocabulary. Put implementation decisions in ADRs or specs.
