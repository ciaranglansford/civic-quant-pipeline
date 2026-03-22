# API and Interfaces

> Legacy sectioned API reference retained for historical context. Prefer `docs/api.md` for current API/runtime interface truth.

## HTTP API Overview

This API supports wire-bulletin ingestion and operational processing jobs.

Opportunity Memo v1 note:
- no new HTTP route is added for v1
- primary interface is CLI job execution
- memo-oriented read models are exposed through DB MCP read-only tools
- canonical memo artifact is investable-thesis structured JSON with required fields:
  - `core_thesis_one_liner`, `opportunity_target`, `market_setup`, `why_this_is_an_opportunity`, `trade_expression`, `quantified_evidence_points`, `invalidation_triggers`, `confidence_level`, and strict traceability mappings

## Current API Surface vs Internal Pipeline Stages

- Exposed HTTP endpoints are focused on ingest and operational triggering.
- Most stage execution (extraction, triage, clustering, reporting) currently runs via jobs/services, not broad public API endpoints.
- A lightweight retrieval endpoint exists for downstream feed consumers.

## Current Implemented Endpoints

### `GET /health`
- Purpose: service liveness.
- Response: `{ "status": "ok" }`.

### `POST /ingest/telegram`
- Purpose: ingest one Telegram bulletin observation.
- Request model: `TelegramIngestPayload`.
- Response model: `IngestResponse`.
- Behavior:
  - validates payload,
  - normalizes text,
  - stores immutable raw record idempotently.

### `POST /ingest/source`
- Purpose: ingest one source-agnostic bulletin observation.
- Request model: `SourceIngestPayload`.
- Response model: `IngestResponse`.
- Behavior:
  - validates payload,
  - normalizes text,
  - maps source payload into a common ingest envelope,
  - namespaces non-Telegram stream identifiers as `<source_type>:<source_stream_id>` to avoid cross-source identity collisions,
  - stores immutable raw record idempotently.

### `POST /admin/process/phase2-extractions`
- Purpose: manual internal trigger for one phase2 extraction run.
- Guard: admin token header.
- Query params:
  - `force_reprocess` (optional bool, default `false`)
- Behavior: runs same extraction processing logic used by scheduled job.
  - `force_reprocess=false`: replay-identity matches reuse existing extraction rows and skip model calls.
  - `force_reprocess=false`: content-reuse matches (same normalized text + extractor contract) can reuse prior canonical extraction across different raw messages.
  - `force_reprocess=true`: bypass replay/content reuse for that run.

### `GET /api/feed/events`
- Purpose: retrieve canonical event feed items for downstream consumers.
- Query params:
  - `limit` (optional)
  - `cursor` (optional)
  - `topic` (optional)
- Response model: `FeedEventsResponse`.
- Behavior:
  - returns event-level summaries ordered by `event_time DESC, id DESC`,
  - supports deterministic cursor pagination.

### `GET /admin/query/events/by-tag`
- Purpose: internal inspection endpoint for structured event retrieval by tag/timeframe.
- Guard: admin token header.
- Query params:
  - `tag_type`, `tag_value`
  - `start_time`, `end_time`
  - optional `min_impact`
  - optional `directionality`
  - optional `limit`
- Behavior: thin wrapper over query helper logic in `app/contexts/events/structured_query.py`.

### `GET /admin/query/events/by-relation`
- Purpose: internal inspection endpoint for structured event retrieval by relation/timeframe.
- Guard: admin token header.
- Query params:
  - `relation_type`
  - `start_time`, `end_time`
  - optional `subject_type`, `subject_value`
  - optional `object_type`, `object_value`
  - optional `min_impact`
  - optional `directionality`
  - optional `limit`
- Behavior: thin wrapper over query helper logic in `app/contexts/events/structured_query.py`.

### Internal Theme Batch Admin Endpoints (`/admin/*`)

These are internal/debug endpoints by convention in this pass (no auth/user system added yet):

- `POST /admin/theme/run`
  - triggers one deterministic theme batch run
  - request includes `theme_key`, optional cadence/window/dry-run/emit-brief
- `GET /admin/themes`
  - lists available theme definitions
- `GET /admin/theme-runs`
  - lists latest persisted runs
- `GET /admin/theme-runs/{run_id}`
  - returns one run record
- `GET /admin/theme-runs/{run_id}/assessments`
  - returns assessments for run
- `GET /admin/theme-runs/{run_id}/thesis-cards`
  - returns cards for run
- `GET /admin/theme-runs/{run_id}/brief`
  - returns brief artifact for run

## Request/Response Contract Notes

### Ingest Request Semantics

`raw_text` is treated as wire bulletin content that may represent an unverified reported claim.

### Ingest Response Semantics

- `status=created`: new raw bulletin captured.
- `status=duplicate`: same source/message identity already captured.

## Non-HTTP Interfaces

### CLI Jobs

- `python -m app.jobs.run_phase2_extraction`
- `python -m app.jobs.run_deep_enrichment`
- `python -m app.jobs.run_digest` (deterministic selection/state + optional LLM synthesis with strict validation/fallback)
- `python -m app.jobs.run_opportunity_memo --start <iso> --end <iso> [--topic <topic>]` (on-demand single-topic memo)
- `python -m app.jobs.adopt_opportunity_memo_schema` (additive schema adoption for memo tables)
- `python -m app.jobs.test_openai_extract`
- `python -m app.jobs.reset_dev_schema`
- `python -m app.jobs.clear_all_but_raw_messages`
- `python -m app.jobs.adopt_stability_contracts`
- `python -m app.jobs.adopt_structured_event_schema`

Runtime ownership note:
- phase2 orchestration entrypoint is `app/workflows/phase2_pipeline.py`
- business rules are context-owned in `app/contexts/*`
- digest/report semantics are canonical in `app/digest/*`
- opportunity memo orchestration entrypoint is `app/workflows/opportunity_memo_pipeline.py`

### DB MCP Read-Model Tools (Opportunity Memo v1)

Added read-only tools:
- `rank_topic_opportunities`
- `build_opportunity_memo_input`
- `get_topic_timeline`
- `get_topic_driver_pack`

Explicitly deferred in v1:
- `get_previous_memo_context`

### Listener Runtime

- `python -m listener.telegram_listener`
- Poll-based loop that fetches unseen messages and posts to ingest endpoint.

## Out of Scope (Current API Surface)

- No public external-validation endpoint yet.
- No broad query API family beyond `GET /api/feed/events`.

