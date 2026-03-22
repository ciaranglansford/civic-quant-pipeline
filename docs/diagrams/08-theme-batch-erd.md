# 08 Theme Batch ERD
Why this diagram matters: It separates reusable theme evidence from per-run analytical outputs so engineers can reason about persistence scope and lineage.

Primary source files used:
- `app/models.py`
- `app/workflows/theme_batch_pipeline.py`
- `app/contexts/themes/evidence.py`
- `app/contexts/opportunities/assessment.py`
- `app/contexts/opportunities/thesis_cards.py`
- `app/contexts/opportunities/briefs.py`

```mermaid
erDiagram
    EVENTS {
        int id PK
        string topic
        float impact_score
        string claim_hash
        datetime event_time
        int latest_extraction_id FK
    }

    EXTRACTIONS {
        int id PK
        int raw_message_id FK
        string claim_hash
        json canonical_payload_json
        datetime created_at
    }

    EVENT_THEME_EVIDENCE {
        int id PK
        string theme_key
        int event_id FK
        int extraction_id FK
        datetime event_time
        float impact_score
        float calibrated_score
        json match_reason_codes
        json metadata_json
    }

    THEME_RUNS {
        int id PK
        string run_key
        string theme_key
        string cadence
        datetime window_start_utc
        datetime window_end_utc
        string status
        int selected_evidence_count
        int assessment_count
        int thesis_card_count
        int suppressed_count
    }

    THEME_OPPORTUNITY_ASSESSMENTS {
        int id PK
        int theme_run_id FK
        string stable_key
        string theme_key
        string primary_lens
        string primary_transmission_pattern
        float evidence_strength_score
        float opportunity_priority_score
        float confidence_score
        string status
    }

    THESIS_CARDS {
        int id PK
        int theme_run_id FK
        int assessment_id FK
        string theme_key
        string narrative_signature
        string status
        string suppression_reason
        string material_update_reason
    }

    THEME_BRIEF_ARTIFACTS {
        int id PK
        int theme_run_id FK
        string theme_key
        string cadence
        string status
        json assessment_ids_json
        json thesis_card_ids_json
    }

    EVENTS ||--o{ EVENT_THEME_EVIDENCE : "evidence rows per theme match"
    EXTRACTIONS ||--o{ EVENT_THEME_EVIDENCE : "optional extraction link"
    THEME_RUNS ||--o{ THEME_OPPORTUNITY_ASSESSMENTS : "run assessments"
    THEME_RUNS ||--o{ THESIS_CARDS : "run cards"
    THEME_RUNS ||--o| THEME_BRIEF_ARTIFACTS : "run brief artifact"
    THEME_OPPORTUNITY_ASSESSMENTS ||--o{ THESIS_CARDS : "assessment cards"
```

## Reading Notes
- `event_theme_evidence` is derived from operational events and can be reused across multiple theme runs.
- `theme_runs` is the batch execution anchor for statuses and aggregate counts.
- Assessments and cards are tied to a specific run via FK, even when content is similar across windows.
- `theme_brief_artifacts` is one-per-run (`theme_run_id` unique).
- Evidence-to-assessment linkage is currently by stored IDs in JSON payloads, not FK join tables.
