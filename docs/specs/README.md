# Version Specifications

Each version has one durable specification. Do not implement a version until its spec is approved.

| Version | Status | Specification |
| --- | --- | --- |
| V0 | Complete | [WhatsApp infrastructure](V0.md) |
| V0.1 | Complete | [Pre-V1 foundation hardening](V0.1.md) |
| V1 | Draft | [AI attendant](V1.md) |

A spec owns detailed scope, user stories, acceptance criteria, test seams, and explicit exclusions. Product purpose stays in `../PRODUCT.md`; sequencing stays in `../ROADMAP.md`; stable trade-offs stay in `../decisions/`.

Use exactly one lifecycle value in each spec: `Status: draft`, `Status: approved`, or `Status: complete`. Only explicit user confirmation changes `draft` to `approved`; creating or editing a spec is not implementation approval. Keep the status in this index synchronized.
