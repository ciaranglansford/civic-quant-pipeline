# Architecture Overview - Civicquant Intelligence Pipeline

> Legacy concise overview retained for context. Prefer `docs/architecture.md` for current canonical module ownership and boundaries.

## Purpose

Provide a concise implementation-truth overview of the current backend architecture.

## Runtime Shape

- One backend repository.
- One FastAPI app entrypoint (`app.main`).
- One shared relational database.
- Background work executed by jobs/workflows, not inline request handlers.

## Current Ownership Map

- `app/routers/*`
  - HTTP adapters only (`/ingest/*`, `/admin/*`, `/api/feed/*`).
- `app/workflows/phase2_pipeline.py`
  - Cross-context orchestration for selection, retries, leases, and run-state transitions.
- `app/contexts/ingest/*`
  - Raw source capture and idempotent raw message persistence.
- `app/contexts/extraction/*`
  - Prompt rendering, LLM client calls, strict schema validation, canonicalization, replay/content reuse logic.
- `app/contexts/triage/*`
  - Deterministic impact calibration, triage actioning, routing, and relatedness checks.
- `app/contexts/events/*`
  - Event matching/upsert and event-message relationship management.
- `app/contexts/entities/*`
  - Entity mention indexing/query helpers.
- `app/contexts/enrichment/*`
  - Enrichment candidate selection and provider seam contracts.
- `app/contexts/feed/*`
  - Feed endpoint query behavior and cursor semantics.
- `app/digest/*`
  - Canonical reporting/digest semantics, synthesis, artifact identity, and destination publication adapters.

## Transitional Compatibility

- Only digest/report shims are retained in `app/services/`:
  - `digest_builder.py`
  - `digest_query.py`
  - `digest_runner.py`
  - `telegram_publisher.py`
- These shims are thin re-export/delegation wrappers with explicit removal TODOs.

## Data Flow (Condensed)

```mermaid
flowchart LR
  tg["Telegram Source"] --> listener["listener.telegram_listener"]
  listener -->|"POST /ingest/telegram"| api["FastAPI Routers"]
  api --> ingest["contexts.ingest"]
  ingest --> db[(DB: raw_messages)]
  jobs["jobs.run_phase2_extraction"] --> wf["workflows.phase2_pipeline"]
  wf --> extraction["contexts.extraction"]
  wf --> triage["contexts.triage"]
  wf --> events["contexts.events"]
  wf --> entities["contexts.entities"]
  wf --> enrich["contexts.enrichment"]
  extraction --> db
  triage --> db
  events --> db
  entities --> db
  enrich --> db
  digestJob["jobs.run_digest"] --> digest["app.digest (canonical)"]
  digest --> db
  digest --> vip["VIP Telegram (adapter)"]
  api --> feed["contexts.feed"] --> db
```
