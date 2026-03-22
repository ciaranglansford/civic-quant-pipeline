# 02 Continuous Pipeline End-to-End
Why this diagram matters: It traces the full continuous control loop from message capture to eventization and downstream indexing, making every write gate and retry boundary explicit.

Primary source files used:
- `app/routers/ingest.py`
- `app/contexts/ingest/ingest_pipeline.py`
- `app/workflows/phase2_pipeline.py`
- `app/contexts/extraction/processing.py`
- `app/contexts/extraction/extraction_validation.py`
- `app/contexts/extraction/canonicalization.py`
- `app/contexts/triage/decisioning.py`
- `app/contexts/events/event_manager.py`
- `app/contexts/events/structured_persistence.py`
- `app/contexts/entities/entity_indexing.py`
- `app/contexts/themes/evidence.py`
- `app/contexts/enrichment/enrichment_selection.py`

```mermaid
sequenceDiagram
    participant Source as "Source listener/backfill"
    participant IngestAPI as "Ingest router"
    participant Ingest as "ingest_pipeline"
    participant DB as "DB"
    participant Phase2 as "phase2_pipeline"
    participant Extract as "extraction.processing"
    participant OpenAI as "OpenAI extraction"
    participant Triage as "triage decisioning"
    participant Events as "event_manager"
    participant Struct as "structured_persistence"
    participant Themes as "themes.evidence"
    participant Enrich as "enrichment_selection"
    participant Entities as "entity_indexing"

    Source->>IngestAPI: POST /ingest/telegram or /ingest/source
    IngestAPI->>Ingest: normalize_message_text() [DET]
    Ingest->>DB: lookup by (source_channel_id, telegram_message_id) [DET]
    alt duplicate message
        Ingest-->>IngestAPI: status=duplicate + existing raw_message_id
    else new message
        Ingest->>DB: insert raw_messages [DET]
        Ingest->>DB: insert message_processing_states(status=pending, attempt_count=0) [DET]
        Ingest-->>IngestAPI: status=created + raw_message_id
    end

    Note over Phase2,DB: Triggered by admin endpoint or run_phase2_extraction job.

    Phase2->>DB: acquire processing_locks('phase2_extraction') [DET]
    alt lock busy
        Phase2-->>Source: run summary (no processing)
    else lock acquired
        Phase2->>DB: select eligible raws (pending|failed|expired in_progress) [DET]
        loop each selected raw_message
            Phase2->>DB: state=in_progress; attempt_count++; last_attempted_at; lease_expires_at [DET]
            Phase2->>Extract: materialize_extraction_for_raw_message()
            alt replay/content reuse hit
                Extract->>DB: reuse canonical extraction payload + calibration metadata [DET]
            else model call required
                Extract->>OpenAI: extract(prompt) [LLM]
                OpenAI-->>Extract: raw JSON
                Extract->>Extract: parse_and_validate_extraction() [DET]
                Extract->>Extract: canonicalize_extraction() + calibrate_impact() [DET]
                Extract->>DB: upsert extractions [DET]
            end

            Phase2->>Triage: compute_routing_decision() [DET]
            alt decision.event_action != ignore
                Phase2->>Events: upsert_event() [DET]
                Events->>DB: create/update/noop event + event_messages link
            else ignore event write
                Note over Phase2,Events: Event row mutation skipped.
            end

            Phase2->>Triage: apply_identity_conflict_override() [DET]
            Phase2->>DB: upsert routing_decisions [DET]

            alt event_id present
                Phase2->>Struct: sync_event_tags_and_relations() [DET]
                Struct->>DB: replace event_tags + event_relations
                Phase2->>Themes: persist_theme_matches_for_event() [DET]
                Themes->>DB: upsert event_theme_evidence
                Phase2->>Enrich: select_and_store_enrichment_candidate() [DET]
                Enrich->>DB: upsert enrichment_candidates
            end

            Phase2->>Entities: index_entities_for_extraction() [DET]
            Entities->>DB: upsert entity_mentions

            alt success
                Phase2->>DB: state=completed; completed_at; lease_expires_at=null
            else validation/provider/persistence error
                Phase2->>DB: state=failed; last_error set
            end
        end
        Phase2->>DB: release processing_locks('phase2_extraction') [DET]
    end
```

## Reading Notes
- The ingest path is deterministic and idempotent on source stream/message identity.
- Only extraction model calls are LLM-assisted; validation and canonicalization are deterministic guards.
- Routing and eventization happen only after a canonical extraction is materialized.
- Structured facets, theme evidence, enrichment candidates, and entity mentions are post-eventization side effects.
- `message_processing_states` is the retry contract; `processing_locks` is run-level exclusivity.
