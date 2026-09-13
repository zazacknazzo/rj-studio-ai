# RJ Studio AI

## Agent skills

### Issue tracker

Issues and specs are tracked as local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.

## Project rules

- Keep provider-specific WhatsApp behavior behind the `WhatsAppProvider` interface.
- Read `CONTEXT.md` before naming domain concepts.
- Read relevant records under `docs/adr/` before changing architecture.
- Keep secrets out of version control; document required values in `.env.example`.
- Run the test suite before considering implementation complete.
