# 06 Core Operational ERD
Why this diagram matters: It provides a focused schema view for the continuous ingest/phase2 loop and digest publishing without mixing in theme-batch-only tables.

Primary source files used:
- `app/models.py`
- `docs/data-model.md`
- `app/workflows/phase2_pipeline.py`
- `app/digest/orchestrator.py`

```mermaid
erDiagram
    RAW_MESSAGES {
        int id PK
        string source_channel_id
        string telegram_message_id
        datetime message_timestamp_utc
        text normalized_text
        datetime created_at
    }

    MESSAGE_PROCESSING_STATES {
        int id PK
        int raw_message_id FK
        string status
        int attempt_count
        datetime last_attempted_at
        datetime completed_at
        datetime lease_expires_at
        text last_error
        string processing_run_id
    }

    PROCESSING_LOCKS {
        string lock_name PK
        datetime locked_until
        string owner_run_id
    }

    EXTRACTIONS {
        int id PK
        int raw_message_id FK
        string extractor_name
        string event_identity_fingerprint_v2
        string canonical_payload_hash
        string claim_hash
        json canonical_payload_json
        datetime created_at
    }

    EVENTS {
        int id PK
        string event_identity_fingerprint_v2
        string topic
        float impact_score
        string action_class
        string claim_hash
        bool review_required
        datetime last_updated_at
        bool is_published_telegram
        bool is_published_twitter
        int latest_extraction_id FK
    }

    EVENT_MESSAGES {
        int id PK
        int event_id FK
        int raw_message_id FK
        datetime linked_at
    }

    EVENT_TAGS {
        int id PK
        int event_id FK
        string tag_type
        string tag_value
        string tag_source
        float confidence
    }

    EVENT_RELATIONS {
        int id PK
        int event_id FK
        string subject_type
        string relation_type
        string object_type
        string relation_source
        int inference_level
    }

    ROUTING_DECISIONS {
        int id PK
        int raw_message_id FK
        json store_to
        string publish_priority
        string event_action
        string triage_action
        json triage_rules
    }

    ENTITY_MENTIONS {
        int id PK
        int raw_message_id FK
        int event_id FK
        string entity_type
        string entity_value
        datetime event_time
    }

    ENRICHMENT_CANDIDATES {
        int id PK
        int event_id FK
        bool selected
        string enrichment_route
        float calibrated_score
        string novelty_state
        datetime scored_at
    }

    EVENT_DEEP_ENRICHMENTS {
        int id PK
        int event_id FK
        string enrichment_route
        json mechanism_notes
        json metadata_json
        datetime created_at
    }

    DIGEST_ARTIFACTS {
        int id PK
        datetime window_start_utc
        datetime window_end_utc
        string canonical_hash
        string input_hash
        datetime created_at
    }

    PUBLISHED_POSTS {
        int id PK
        int artifact_id FK
        int event_id FK
        string destination
        string status
        datetime last_attempted_at
        datetime published_at
        string content_hash
    }

    RAW_MESSAGES ||--o| MESSAGE_PROCESSING_STATES : "state by raw_message_id"
    RAW_MESSAGES ||--o| EXTRACTIONS : "extraction by raw_message_id"
    RAW_MESSAGES ||--o| ROUTING_DECISIONS : "decision by raw_message_id"
    RAW_MESSAGES ||--o{ EVENT_MESSAGES : "linked raw messages"
    EVENTS ||--o{ EVENT_MESSAGES : "linked events"
    EVENTS ||--o{ EVENT_TAGS : "tags"
    EVENTS ||--o{ EVENT_RELATIONS : "relations"
    EXTRACTIONS ||--o{ EVENTS : "latest_extraction_id"
    RAW_MESSAGES ||--o{ ENTITY_MENTIONS : "entity mentions"
    EVENTS ||--o{ ENTITY_MENTIONS : "optional event link"
    EVENTS ||--o| ENRICHMENT_CANDIDATES : "enrichment candidate"
    EVENTS ||--o| EVENT_DEEP_ENRICHMENTS : "deep enrichment"
    DIGEST_ARTIFACTS ||--o{ PUBLISHED_POSTS : "artifact publications"
    EVENTS ||--o{ PUBLISHED_POSTS : "optional event reference"
```

## Reading Notes
- `raw_messages` is the ingest anchor; most continuous tables trace back to it directly or through `events`.
- `message_processing_states` is one-row-per-raw and drives phase2 eligibility and retries.
- `events.latest_extraction_id` is a nullable pointer, not a strict one-to-one contract.
- Digest publication state is artifact-centric (`digest_artifacts` -> `published_posts`).
- `processing_locks` is intentionally separate from row models and acts as workflow exclusivity control.
