# Civicquant Documentation

This directory contains source-of-truth operational and architecture docs for the current codebase.

## Start Here

1. [`architecture.md`](./architecture.md)
2. [`system-flow.md`](./system-flow.md)
3. [`local-development.md`](./local-development.md)
4. [`configuration.md`](./configuration.md)
5. [`api.md`](./api.md)
6. [`data-model.md`](./data-model.md)
7. [`operations.md`](./operations.md)
8. [`troubleshooting.md`](./troubleshooting.md)
9. [`glossary.md`](./glossary.md)

## Canonical Docs

- [`architecture.md`](./architecture.md): module ownership, boundaries, and runtime topology.
- [`system-flow.md`](./system-flow.md): end-to-end flow from ingest to digest/theme outputs.
- [`local-development.md`](./local-development.md): setup, run order, and test commands.
- [`configuration.md`](./configuration.md): environment variable reference from runtime code.
- [`api.md`](./api.md): HTTP routes and non-HTTP operational interfaces.
- [`data-model.md`](./data-model.md): table contracts and key relationships.
- [`operations.md`](./operations.md): job runbook, scheduling, and safety rules.
- [`troubleshooting.md`](./troubleshooting.md): common failure modes and checks.
- [`glossary.md`](./glossary.md): domain terminology.
- [`../app/jobs/README.md`](../app/jobs/README.md): full job matrix and command-specific notes.

## Historical and Planning Artifacts

These directories are intentionally retained but are not the primary source for current runtime behavior:

- `docs/00-current-state/`
- `docs/01-overview/`
- `docs/02-flows/`
- `docs/03-architecture/`
- `docs/03-interfaces/`
- `docs/04-operations/`
- `docs/05-audit/`
- `docs/feed-api/`
- `docs/10-roadmap/`
- `docs/20-work-registry/`
- `docs/30-decisions/`
- `plans/`
- `user-stories/`

Use these as historical context or backlog material. For implementation truth, prefer the canonical docs listed above and the code modules they reference.

