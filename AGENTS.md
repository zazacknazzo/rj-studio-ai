# RJ Studio AI

## Agent skills

- Local issue workflow: `docs/agents/issue-tracker.md`.
- Domain documentation rules: `docs/agents/domain.md`.

## Load context on demand

Read only the documents needed for the task:

- Product behavior or scope: `docs/PRODUCT.md` and the relevant part of `docs/ROADMAP.md`.
- Domain language: `docs/CONTEXT.md`.
- Code, data, or integrations: `docs/ARCHITECTURE.md` and only the relevant ADR from `docs/decisions/`.
- Version work: the matching file in `docs/specs/`.
- LLM behavior: the matching specification plus `docs/evals/README.md` and its version suite.

Do not preload the whole `docs/` tree.

## Invariants

- V0–V6 serve one business: RJ Studio. Multi-business SaaS begins at V7.
- Do not build tenant infrastructure before V7. Keep schemas and interfaces migratable to a future `tenant_id`.
- Keep RJ Studio facts, tone, offers, and commercial policies out of generic orchestration logic.
- Put external systems behind adapters/providers. Twilio must remain replaceable by Meta Cloud API.
- Add a seam only when variation or critical testing justifies it. Avoid generic repositories and speculative layers.
- Build complete vertical slices. Test observable behavior at critical seams.
- Record hard-to-reverse, non-obvious trade-offs as concise ADRs in `docs/decisions/`.
- Never commit secrets or real customer data.
- A version requires an approved spec before implementation.

## Git discipline

- GitHub is the remote source of truth.
- Never commit secrets, `.env`, real customer data, or local databases containing real data.
- Work should be committed in small, coherent changes.
- Non-trivial version work should occur on a feature branch.
- Keep `main` in a known-good state.
- Do not rewrite published history without explicit approval.

## Working loop

1. Read the relevant spec, code, glossary terms, and ADRs.
2. Confirm the highest useful test seam before changing behavior.
3. Implement one vertical slice and keep tests green.
4. Update durable docs only when product, architecture, vocabulary, or a stable decision changed.
5. Run all checks before completion.

## Commands

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/uvicorn rj_studio_ai.main:app --reload --port 8000
```

Environment variables and Twilio Sandbox setup live in `README.md` and `.env.example`.
