# Issue tracker: Local Markdown

Implementation tickets live as local Markdown files in `.scratch/`. Durable version specs live in `docs/specs/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The durable spec is `docs/specs/V<N>.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`
- Ticket state is recorded as `Status: ready-for-agent`, `in-progress`, `blocked`, or `done`
- Comments and conversation history append under a `## Comments` heading

## Publishing and fetching

When a skill says to publish tickets, create files under `.scratch/<feature-slug>/issues/`. When it says to publish a version spec, create or update `docs/specs/V<N>.md` and link it from `docs/specs/README.md`.

When a skill says to fetch a ticket, read the referenced local Markdown file.

Move a ticket from `ready-for-agent` to `in-progress` when work begins, to `blocked` only with a recorded blocker, and to `done` only after its acceptance criteria and required checks pass.
