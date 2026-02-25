## Phase 1 MVP Roadmap – Civicquant Intelligence Pipeline

### Purpose

Provide a concise, execution-focused roadmap for the Phase 1 MVP aligned with the Civicquant specification JSON. This is the top-level reference for what “done” means in Phase 1.

### Scope

- **Includes**: Telegram ingestion, storage, structured extraction stub, basic routing, basic dedup/event upsert, and 4-hour VIP digest generation.
- **Excludes**: Evidence/corroboration service, reliability scoring, embeddings/pgvector, multi-channel routing, Twitter/blog/short-form publishing.

### Objectives

- **O1 – Reliable Telegram ingestion**
  - Single MTProto user client attached to one external Telegram channel.
  - Every new message (1–5 min cadence) is captured with metadata and sent to the backend ingest endpoint.
  - Idempotency by `source_channel_id + telegram_message_id`.

- **O2 – Structured storage of all messages**
  - Persist immutable raw messages.
  - Normalize text for downstream dedup.
  - Store per-message extraction results (stubbed LLM) in a separate table with model version.

- **O3 – Basic extraction and routing**
  - Implement an `ExtractionAgent` stub that:
    - Accepts `normalized_text`, `message_time`, and `source_channel_name`.
    - Produces JSON aligned with the `llm_extraction_schema` fields (topics, entities, impact, breaking flags, fingerprint).
  - Implement a rules-based routing layer that:
    - Maps extraction outputs to destinations.
    - Assigns `publish_priority`, `requires_evidence`, `event_action`, and `flags`.
    - Uses **hard rules only** in Phase 1.

- **O4 – Dedup + canonical events**
  - Maintain an `events` table with a single canonical record per event.
  - Deduplicate based on `event_fingerprint` + configured time windows.
  - Append new messages to existing events and update important fields (impact, summary, etc.) deterministically.

- **O5 – 4-hour VIP digests**
  - Query events from the last 4 hours by category/topic.
  - Generate a category-grouped digest summarizing events with 1-sentence summaries, key facts, and corroboration labels (stubbed/unknown in Phase 1).
  - Post digests to a VIP Telegram chat and store an audit record of each published digest.

### Feature Mapping (from specification)

- **Telegram Listener (MTProto)** – status: `planned`
  - Dependencies: Telegram API credentials, Telethon, session management.

- **Backend Ingest Endpoint** – status: `planned`
  - Dependencies: FastAPI app, DB connection, idempotency keys.

- **LLM Structured Extraction (stubbed)** – status: `planned`
  - Dependencies: schema validator, deterministic stub logic (or simple LLM integration later).

- **Rules Engine (Logic Gates)** – status: `planned`
  - Dependencies: versioned config file or in-code defaults, thresholds.

- **Dedup + Event Upsert** – status: `planned`
  - Dependencies: event fingerprint, time windows, basic similarity rules.

- **Scheduled VIP Digests** – status: `planned`
  - Dependencies: query layer, digest templates, Telegram bot posting.

### Non-Functional Requirements (Phase 1)

- **Accuracy over speed**: Favor correctness and determinism over ultra-low latency.
- **Latency target**: ≤ 30 seconds end-to-end from ingest to internal availability (not including scheduled digest).
- **Idempotency**:
  - Repeated ingest calls with the same `source_channel_id + telegram_message_id` must not create duplicate raw messages.
  - Event deduplication must avoid creating multiple canonical events for the same fingerprint within a time window.
- **Cost controls**: No evidence or heavy multi-source synthesis in Phase 1.
- **Safety and auditability**:
  - No prescriptive trading advice in any output.
  - Maintain an audit trail linking published digests back to events and raw messages.

### Dependencies and Assumptions

- **Database**: Single Postgres instance with tables:
  - `raw_messages`, `extractions`, `events`, `event_messages`, `routing_decisions`, `published_posts`.
- **Backend**: Python + FastAPI.
- **Listener**: Python + Telethon MTProto user client, authenticated as the owner.
- **Publishing**: Telegram bot for VIP channel with bot token and chat ID.
- **Scheduling**: OS cron or simple loop for digests in Phase 1; more advanced job system later.

### Exit Criteria for Phase 1 MVP

- **E1 – Ingestion**
  - All messages from the configured Telegram channel over a 24-hour period appear in `raw_messages` with no duplicates and correct timestamps.

- **E2 – Extraction + Storage**
  - For every `raw_messages` row, an `extractions` row exists with valid JSON conforming to the extraction schema (allowing stubbed values where appropriate).

- **E3 – Events and Dedup**
  - Near-duplicate headlines (same event_fingerprint within window) appear as a **single event** with multiple linked messages.
  - Example duplicate scenarios (e.g., same Pentagon plan, same S&P note) result in a single canonical event.

- **E4 – Routing**
  - Each raw message has an associated `routing_decisions` record with deterministic `store_to`, `publish_priority`, and `event_action`.

- **E5 – VIP Digest**
  - A 4-hour digest can be generated on demand, posted to the VIP Telegram chat, and traced back to underlying events and raw messages.

