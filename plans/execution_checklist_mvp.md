## Phase 1 MVP Execution Checklist

This checklist tracks implementation of the Phase 1 MVP. Each item uses the format:

- **Pattern**: `[status] ID (area) - description`
- **Status values**: `pending`, `in_progress`, `done`, `blocked`

### Global Conventions

- **Idempotency**: All ingestion and event operations must be safe to retry.
- **Determinism**: Routing and dedup decisions must be reproducible from inputs and configuration.
- **No trading advice**: Outputs must not contain prescriptive trading recommendations.

### Ingestion – Telegram Listener (MTProto)

- [pending] ING-01 (ingestion) - Configure Telethon client with API credentials and session storage.
- [pending] ING-02 (ingestion) - Implement subscription to a single source Telegram channel by username or ID.
- [pending] ING-03 (ingestion) - On each new message, build payload with all required fields from the spec.
- [pending] ING-04 (ingestion) - POST payload to `/ingest/telegram` with retries on transient failures.
- [pending] ING-05 (ingestion) - Log ingest successes and failures with minimal structured fields.

### Backend – Ingest Endpoint and Storage

- [pending] BE-01 (backend_ingest) - Define `TelegramIngestPayload` schema mirroring the spec fields.
- [pending] BE-02 (backend_ingest) - Implement `/ingest/telegram` FastAPI endpoint with request validation.
- [pending] BE-03 (backend_ingest) - Implement deterministic message normalization function.
- [pending] BE-04 (backend_ingest) - Persist raw messages as immutable rows in `raw_messages`.
- [pending] BE-05 (backend_ingest) - Enforce idempotency on `(source_channel_id, telegram_message_id)` via DB constraint and application logic.
- [pending] BE-06 (backend_ingest) - Store `normalized_text` alongside raw fields.

### Extraction – Structured JSON (Stubbed)

- [pending] EXT-01 (extraction) - Implement `ExtractionAgent` service interface with clear input/output types.
- [pending] EXT-02 (extraction) - Implement stub extraction that produces valid JSON conforming to `llm_extraction_schema`.
- [pending] EXT-03 (extraction) - Store extraction results in `extractions` table with `model_name` and timestamps.
- [pending] EXT-04 (extraction) - Validate extraction JSON before storage and log validation errors.

### Routing – Logic Gates

- [pending] ROUT-01 (routing) - Implement a configuration structure (in-code or YAML/JSON) for routing thresholds and destinations.
- [pending] ROUT-02 (routing) - Implement routing function that maps extraction outputs to:
  - `store_to` (destinations),
  - `publish_priority`,
  - `requires_evidence`,
  - `event_action`,
  - `flags`.
- [pending] ROUT-03 (routing) - Persist routing decisions in `routing_decisions` table for every ingested message.
- [pending] ROUT-04 (routing) - Ensure routing is deterministic given the same extraction and configuration.

### Dedup + Event Upsert

- [pending] EVT-01 (events) - Define event model fields including `event_fingerprint`, `topic`, `summary_1_sentence`, `impact_score`, `is_breaking`, `breaking_window`, `event_time`.
- [pending] EVT-02 (events) - Implement function to compute event time windows (default, breaking, macro_econ).
- [pending] EVT-03 (events) - Implement create/update/ignore logic based on `event_fingerprint` and time window.
- [pending] EVT-04 (events) - Implement `event_messages` linking table between events and raw messages.
- [pending] EVT-05 (events) - Update event record when new numeric facts or entities appear, preserving previous state via timestamps.
- [pending] EVT-06 (events) - Log event update actions, including why an event was updated or created.

### Storage Model and Indexing

- [pending] DB-01 (storage) - Create tables: `raw_messages`, `extractions`, `events`, `event_messages`, `routing_decisions`, `published_posts`.
- [pending] DB-02 (storage) - Add unique constraint on `(source_channel_id, telegram_message_id)` in `raw_messages`.
- [pending] DB-03 (storage) - Add time-based indexes for message and event queries.
- [pending] DB-04 (storage) - Add index on `event_fingerprint` in `events`.

### Publishing – 4-Hour VIP Digests

- [pending] PUB-01 (publishing) - Implement query to fetch events in the last `VIP_DIGEST_HOURS` hours grouped by topic.
- [pending] PUB-02 (publishing) - Implement digest text generator enforcing:
  - 1-sentence summary per item.
  - Key numeric facts and entities.
  - Corroboration label (stubbed to `unknown` or simple rule in Phase 1).
- [pending] PUB-03 (publishing) - Implement Telegram bot sender that posts digest text to VIP chat.
- [pending] PUB-04 (publishing) - Persist each published digest in `published_posts` with `destination`, `content`, `content_hash`, and `published_at`.

### Observability and Audit

- [pending] OBS-01 (observability) - Log ingest success/failure with request ID and telegram identifiers.
- [pending] OBS-02 (observability) - Log extraction success/failure and validation status.
- [pending] OBS-03 (observability) - Log routing decisions including which rules fired.
- [pending] OBS-04 (observability) - Log dedup decisions including candidate events considered and chosen.
- [pending] OBS-05 (observability) - Log published digests with references to event IDs included.

