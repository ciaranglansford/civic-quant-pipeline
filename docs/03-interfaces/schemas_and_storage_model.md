## Schemas and Storage Model

### Purpose

Summarize key JSON schemas and the Postgres storage model used in the Civicquant Intelligence Pipeline.

### Extraction Schema (llm_extraction_schema)

- **topic: string(enum)**
  - One of:
    - `macro_econ`, `central_banks`, `equities`, `credit`, `rates`, `fx`, `commodities`, `crypto`, `war_security`, `geopolitics`, `company_specific`, `other`

- **entities: object**
  - `countries: string[]`
  - `orgs: string[]`
  - `people: string[]`
  - `tickers: string[]`

- **affected_countries_first_order: string[]**

- **market_stats: object[]**
  - Each object:
    - `label: string`
    - `value: number`
    - `unit: string`
    - `context: string`

- **sentiment: string(enum)**
  - `positive`, `negative`, `neutral`, `mixed`, `unknown`

- **confidence: number**
  - Range: `0..1`

- **impact_score: number**
  - Range: `0..100`

- **is_breaking: boolean**

- **breaking_window: string(enum)**
  - `15m`, `1h`, `4h`, `none`

- **event_time: string(ISO8601) | null**

- **source_claimed: string | null**

- **summary_1_sentence: string**

- **keywords: string[]**

- **event_fingerprint: string**
  - Stable key constructed from entities, numbers, topic, and source.

### Evidence Schema (Phase 2+)

- **evidence_sources: object[]**
  - Each object:
    - `publisher: string`
    - `title: string`
    - `url: string`
    - `published_time: string(ISO8601) | null`
    - `snippet: string`

- **corroboration_status: string(enum)**
  - `corroborated`, `partially_corroborated`, `uncorroborated`, `unknown`

- **reliability_score: number**
  - Range: `0..100`

- **notes: string**

### Postgres Tables

#### raw_messages

- **Purpose**: Immutable store of every ingested Telegram message.
- **Key columns**:
  - `id` (PK, integer)
  - `source_channel_id` (string)
  - `source_channel_name` (string, nullable)
  - `telegram_message_id` (string)
  - `message_timestamp_utc` (timestamp)
  - `raw_text` (text)
  - `raw_entities` (JSON, nullable)
  - `forwarded_from` (string, nullable)
  - `normalized_text` (text)
  - `created_at` (timestamp)
- **Constraints / Indexes**:
  - Unique constraint on `(source_channel_id, telegram_message_id)`.
  - Index on `message_timestamp_utc`.

#### extractions

- **Purpose**: Per-message structured extraction and model metadata.
- **Key columns**:
  - `id` (PK, integer)
  - `raw_message_id` (FK -> raw_messages.id)
  - `model_name` (string)
  - `extraction_json` (JSON)
  - `created_at` (timestamp)
- **Constraints / Indexes**:
  - Foreign key constraint to `raw_messages`.
  - Optional unique constraint on `raw_message_id` (one extraction per message in Phase 1).

#### events

- **Purpose**: Canonical evolving records for deduplicated events.
- **Key columns**:
  - `id` (PK, integer)
  - `event_fingerprint` (string)
  - `topic` (string)
  - `summary_1_sentence` (text)
  - `impact_score` (numeric)
  - `is_breaking` (boolean)
  - `breaking_window` (string)
  - `event_time` (timestamp)
  - `last_updated_at` (timestamp)
  - `latest_extraction_id` (FK -> extractions.id, nullable)
- **Constraints / Indexes**:
  - Index on `event_fingerprint`.
  - Index on `event_time`.

#### event_messages

- **Purpose**: Join table linking raw messages to events.
- **Key columns**:
  - `id` (PK, integer)
  - `event_id` (FK -> events.id)
  - `raw_message_id` (FK -> raw_messages.id)
  - `linked_at` (timestamp)
- **Constraints / Indexes**:
  - Unique constraint on `(event_id, raw_message_id)` to avoid duplicate links.

#### routing_decisions

- **Purpose**: Record routing outcomes for each message.
- **Key columns**:
  - `id` (PK, integer)
  - `raw_message_id` (FK -> raw_messages.id)
  - `store_to` (JSON array of strings)
  - `publish_priority` (string)
  - `requires_evidence` (boolean)
  - `event_action` (string)
  - `flags` (JSON array of strings)
  - `created_at` (timestamp)
- **Constraints / Indexes**:
  - Foreign key constraint to `raw_messages`.

#### published_posts

- **Purpose**: Audit log of what content was published where and when.
- **Key columns**:
  - `id` (PK, integer)
  - `event_id` (FK -> events.id, nullable)
  - `destination` (string)
  - `published_at` (timestamp)
  - `content` (text)
  - `content_hash` (string)
- **Constraints / Indexes**:
  - Index on `content_hash`.
  - Index on `published_at`.

### Indexing Summary

- Time-based indexes:
  - `raw_messages.message_timestamp_utc`
  - `events.event_time`
  - `published_posts.published_at`
- Fingerprint index:
  - `events.event_fingerprint`
- Uniqueness:
  - `raw_messages(source_channel_id, telegram_message_id)`
  - `event_messages(event_id, raw_message_id)`


### Phase 2 Validation Rules (ExtractionAgent)

- Parse LLM response as a single JSON object only.
- Reject payloads with unknown fields.
- Enforce enum membership for `topic`, `sentiment`, and `breaking_window`.
- Enforce numeric ranges:
  - `confidence` in `[0,1]`
  - `impact_score` in `[0,100]`
- Persist validation failure reason into processing-state records; do not write invalid extraction rows.

### message_processing_states (Phase 2)

- **Purpose**: Track scheduled extraction status, retries, leases, and run traceability per raw message.
- **Key columns**:
  - `id` (PK)
  - `raw_message_id` (FK -> `raw_messages.id`, unique)
  - `status` (`pending|in_progress|completed|failed`)
  - `attempt_count` (integer)
  - `lease_expires_at` (timestamp, nullable)
  - `last_attempted_at` (timestamp, nullable)
  - `completed_at` (timestamp, nullable)
  - `processing_run_id` (string, nullable)
  - `last_error` (text, nullable)
- **Constraints / Indexes**:
  - Unique on `raw_message_id`.
  - Indexes on (`status`, `lease_expires_at`) to support 10-minute selector queries.

### extractions traceability extension (Phase 2)

In addition to existing fields, extraction persistence should include:
- `prompt_version`
- `processing_run_id`
- `llm_raw_response`
- `validated_at`

These fields support replay/debug of model behavior and run-level audits.
