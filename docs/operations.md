# Operations Runbook

## Core Jobs

| Job | Command | Main effect |
|---|---|---|
| Phase2 extraction | `python -m app.jobs.run_phase2_extraction` | Processes eligible raw messages into extraction/triage/event/entity outputs. |
| Deep enrichment | `python -m app.jobs.run_deep_enrichment` | Materializes Pass B `deep_enrich` outputs for selected candidates. |
| Digest | `python -m app.jobs.run_digest` | Builds canonical digest artifacts and attempts destination publish. |
| Theme batch | `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily` | Runs deterministic thematic batch and persists run/evidence/assessment/card/brief artifacts. |
| Pipeline inspect | `python -m app.jobs.inspect_pipeline --limit 20` | Prints recent pipeline lineage. |

See `app/jobs/README.md` for the complete list (including schema adoption/reset utilities).

## Suggested Schedule

- Phase2 extraction: every 10 minutes.
- Deep enrichment: every 10-30 minutes (or after phase2).
- Digest: every `VIP_DIGEST_HOURS` (default 4).
- Theme batch:
  - daily run once/day
  - weekly run once/week

## Important Invariants

- Digest artifact must be persisted before publish attempt.
- Phase2 and deep enrichment each use `processing_locks` to avoid overlapping runs.
- Phase2 admin trigger requires `PHASE2_ADMIN_TOKEN` and `x-admin-token` header.

## Data Reset and Safety

Clear derived data but keep raw ingest history:

```bash
CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages
```

Full destructive reset:

```bash
python -m app.jobs.reset_dev_schema
```

Notes:
- `clear_all_but_raw_messages` enforces `CONFIRM_CLEAR_NON_RAW=true`.
- `reset_dev_schema` is destructive and currently has no active runtime confirmation guard.

## Operational Checks

After phase2:
- confirm `message_processing_states` moved to `completed` or `failed`
- confirm new rows in `extractions`, `routing_decisions`, `events`, `event_messages`
- review `extractions.metadata_json.impact_scoring` for calibration behavior

After digest:
- confirm `digest_artifacts` row exists
- confirm `published_posts` row(s) for destination status
- if destination is configured and publish succeeds, confirm event publish flags updated

After theme batch:
- confirm `theme_runs` status
- confirm run-linked rows in assessments/cards/brief

## Logging Anchors

Useful logger names:
- `civicquant.ingest`
- `civicquant.phase2`
- `civicquant.events`
- `civicquant.digest`
- `civicquant.theme_batch`
- `civicquant.deep_enrichment`
