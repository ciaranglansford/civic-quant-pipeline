# API and Interfaces

## HTTP Routes

### `GET /health`

- Response: `{"status":"ok"}`
- Model: `HealthResponse`

### `POST /ingest/telegram`

- Router: `app/routers/ingest.py`
- Request model: `TelegramIngestPayload`
- Response model: `IngestResponse`
- Behavior:
  - normalizes `raw_text`
  - writes `raw_messages` idempotently
  - creates `message_processing_states` (`pending`) for new rows
  - returns `status=created` or `status=duplicate`

### `POST /ingest/source`

- Router: `app/routers/ingest.py`
- Request model: `SourceIngestPayload`
- Response model: `IngestResponse`
- Behavior:
  - same ingest pipeline as Telegram route
  - non-Telegram source IDs are namespaced (`<source_type>:<source_stream_id>`) to avoid collisions

### `POST /admin/process/phase2-extractions`

- Router: `app/routers/admin.py`
- Query params:
  - `force_reprocess` (bool, default `false`)
- Header required:
  - `x-admin-token`
- Auth rule:
  - must match `PHASE2_ADMIN_TOKEN`
  - if token is unset, endpoint is effectively disabled and returns `401`
- Behavior:
  - runs one phase2 batch (`process_phase2_batch`)
  - commits batch summary

### `GET /admin/query/events/by-tag`

- Router: `app/routers/admin.py`
- Header required: `x-admin-token` (`PHASE2_ADMIN_TOKEN`)
- Query params:
  - `tag_type`, `tag_value`
  - `start_time`, `end_time`
  - optional `min_impact`, `directionality`, `limit`
- Returns serialized event records from `app/contexts/events/structured_query.py`

### `GET /admin/query/events/by-relation`

- Router: `app/routers/admin.py`
- Header required: `x-admin-token` (`PHASE2_ADMIN_TOKEN`)
- Query params:
  - `relation_type`
  - `start_time`, `end_time`
  - optional `subject_type`, `subject_value`, `object_type`, `object_value`
  - optional `min_impact`, `directionality`, `limit`

### `GET /api/feed/events`

- Router: `app/routers/feed.py`
- Query params:
  - `limit` (`1..100`, default `30`)
  - `cursor` (opaque deterministic cursor)
  - `topic` (optional typed topic enum)
- Response model: `FeedEventsResponse`
- Behavior:
  - filters to events with non-empty summary and valid topic
  - orders by `event_time DESC, id DESC`
  - returns deterministic cursor pagination
  - invalid cursor returns `400`

### Theme Admin Routes (`/admin/*`)

Router: `app/routers/admin_theme.py`

Endpoints:
- `POST /admin/theme/run`
- `GET /admin/themes`
- `GET /admin/theme-runs`
- `GET /admin/theme-runs/{run_id}`
- `GET /admin/theme-runs/{run_id}/assessments`
- `GET /admin/theme-runs/{run_id}/thesis-cards`
- `GET /admin/theme-runs/{run_id}/brief`

Current auth status:
- no auth guard is implemented for these routes in current code
- treat as internal-only endpoints by deployment convention

## Non-HTTP Operational Interfaces

Primary job entrypoints:
- `python -m app.jobs.run_phase2_extraction`
- `python -m app.jobs.run_deep_enrichment`
- `python -m app.jobs.run_digest`
- `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily`
- `python -m app.jobs.inspect_pipeline --limit 20`
- `python -m app.jobs.test_openai_extract`

Listener:
- `python -m listener.telegram_listener`

See `app/jobs/README.md` for the full job matrix and reset/adoption scripts.
