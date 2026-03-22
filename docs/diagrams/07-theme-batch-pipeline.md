# 07 Theme Batch Pipeline
Why this diagram matters: It shows the full batch orchestration path, including cadence/window resolution, lock behavior, evidence catch-up, and run status outcomes.

Primary source files used:
- `app/routers/admin_theme.py`
- `app/jobs/run_theme_batch.py`
- `app/workflows/theme_batch_pipeline.py`
- `app/contexts/themes/evidence.py`
- `app/contexts/themes/bundle.py`
- `app/contexts/opportunities/providers.py`
- `app/contexts/opportunities/assessment.py`
- `app/contexts/opportunities/thesis_cards.py`
- `app/contexts/opportunities/briefs.py`

```mermaid
flowchart TD
    API["Admin trigger: POST /admin/theme/run"] --> START["run_theme_batch(request)"]
    CLI["CLI trigger: python -m app.jobs.run_theme_batch"] --> START

    START --> VALIDATE["Validate theme_key and cadence support"]
    VALIDATE --> WINDOW["Resolve window from request or cadence default"]
    WINDOW --> RUNROW["Insert theme_runs row status=running"]
    RUNROW --> LOCK{"Acquire lock\nprocessing_locks lock_name=theme_batch:{theme}:{cadence}?"}

    LOCK -->|no| BUSY["Set theme_runs.status=skipped_lock_busy\nerror_message=lock busy"]
    BUSY --> OUT_BUSY["Return summary: skipped_lock_busy"]

    LOCK -->|yes| CATCHUP["ensure_theme_evidence_for_window()\ninsert missing event_theme_evidence"]
    CATCHUP --> BUNDLE["build_evidence_bundle()\ndedupe + freshness + severity profiles"]
    BUNDLE --> ENRICH["InternalEvidenceAggregationProvider.enrich()\n[DET]"]
    ENRICH --> ASSESS["create_assessments_for_bundle()\npersist theme_opportunity_assessments"]
    ASSESS --> CARDS["create_cards_for_assessments()\npersist thesis_cards"]
    CARDS --> BRIEF["build_and_persist_brief_artifact()\npersist theme_brief_artifacts"]
    BRIEF --> COMPLETE["Update theme_runs counters\nstatus=completed"]
    COMPLETE --> RELEASE["Release theme lock"]
    RELEASE --> OUT_OK["Return summary: completed"]

    CATCHUP -->|exception| FAIL["Set theme_runs.status=failed\nstore error_message"]
    BUNDLE -->|exception| FAIL
    ENRICH -->|exception| FAIL
    ASSESS -->|exception| FAIL
    CARDS -->|exception| FAIL
    BRIEF -->|exception| FAIL
    COMPLETE -->|exception| FAIL
    FAIL --> RELEASE
    FAIL --> OUT_FAIL["Return summary: failed"]
```

## Reading Notes
- Theme batch can be triggered from API or CLI, but both paths converge on `run_theme_batch`.
- The workflow always creates a `theme_runs` row first, then decides `completed`, `failed`, or `skipped_lock_busy`.
- Locking is per theme and cadence (`theme_batch:{theme}:{cadence}`), not global.
- Enrichment in this pipeline is internal deterministic aggregation, not an external LLM call.
- Evidence is reusable (`event_theme_evidence`), while assessments/cards/brief are run-scoped outputs.
