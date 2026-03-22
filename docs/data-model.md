# Data Model

Primary schema definitions live in `app/models.py`.

## Core Ingest and Processing Tables

### `raw_messages`

- Immutable source rows.
- Unique key: `(source_channel_id, telegram_message_id)`.
- Stores raw text plus deterministic `normalized_text`.

### `message_processing_states`

- One row per raw message (`raw_message_id` unique).
- Tracks extraction lifecycle:
  - `pending`
  - `in_progress` (lease-based)
  - `completed`
  - `failed`

### `processing_locks`

- Named workflow locks (`phase2_extraction`, `deep_enrichment`, theme locks).
- Columns: `lock_name`, `locked_until`, `owner_run_id`.

### `extractions`

- One row per raw message (`raw_message_id` unique).
- Stores:
  - typed extraction fields (`topic`, `impact_score`, `event_time`, etc.)
  - raw validated payload (`payload_json`)
  - canonicalized payload (`canonical_payload_json`)
  - metadata/telemetry (`metadata_json`)
  - replay/content identity fields (`normalized_text_hash`, `replay_identity_key`, `canonical_payload_hash`, `claim_hash`)

## Event and Routing Tables

### `events`

- Canonical evolving event records.
- Identity constraint: `event_identity_fingerprint_v2` unique (nullable).
- Tracks publication flags and review markers (`review_required`, `review_reason`).

### `event_messages`

- Link table between events and raw observations.
- Unique key: `(event_id, raw_message_id)`.

### `routing_decisions`

- One routing/triage row per raw message (`raw_message_id` unique).
- Stores:
  - destination routing (`store_to`)
  - publish priority/evidence flags
  - event action (`create|update|ignore`)
  - triage action + fired triage rules

### `event_tags` and `event_relations`

- Normalized structured facets derived from canonical extraction output.
- Replaced per event on sync (`sync_event_tags_and_relations`).
- Both enforce dedupe uniqueness at row shape level.

### `entity_mentions`

- Normalized entity index (`country`, `org`, `person`, `ticker`).
- Unique key: `(raw_message_id, entity_type, entity_value)`.
- Supports retrieval slicing by topic/time/breaking.

## Enrichment Tables

### `enrichment_candidates`

- Deterministic enrichment selection outcome per event (`event_id` unique).
- Captures route (`store_only|index_only|deep_enrich`), novelty state, and score context.

### `event_deep_enrichments`

- Pass B enrichment output (one row per event).
- Stores structured hints/notes arrays and metadata.

## Digest Tables

### `digest_artifacts`

- Persisted canonical digest output.
- Identity fields:
  - `input_hash` (stable source-input identity)
  - `canonical_hash` (rendered text hash)

### `published_posts`

- Per-destination publish outcomes for each artifact.
- Unique key: `(artifact_id, destination)`.
- Tracks status, content hash, errors, and external reference.

## Theme Batch Tables

### `theme_runs`

- Batch run lifecycle record (`run_key` unique).
- Stores status, window bounds, and counts.

### `event_theme_evidence`

- Deterministic evidence matches between events and themes.
- Unique key: `(theme_key, event_id, extraction_id)`.

### `theme_opportunity_assessments`

- Persisted scored assessments per run/lens.
- Unique key: `stable_key`.

### `thesis_cards`

- Emitted/suppressed/draft card outputs derived from assessments.
- Includes narrative signature for duplicate suppression logic.

### `theme_brief_artifacts`

- One brief per run (`theme_run_id` unique).
- Stores summary and linked assessment/card ids.

## Relationship Summary

- `raw_messages` -> `extractions` (1:1)
- `raw_messages` -> `routing_decisions` (1:1)
- `raw_messages` -> `message_processing_states` (1:1)
- `raw_messages` -> `event_messages` (1:N link rows)
- `events` <- `event_messages` -> `raw_messages` (N:M via link)
- `events` -> `event_tags` / `event_relations` / `entity_mentions` / `enrichment_candidates` / `event_deep_enrichments`
- `digest_artifacts` -> `published_posts`
- `theme_runs` -> `theme_opportunity_assessments` / `thesis_cards` / `theme_brief_artifacts`
