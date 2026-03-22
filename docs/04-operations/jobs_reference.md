# Jobs Reference

> Legacy sectioned job reference retained for context. Prefer `app/jobs/README.md` plus `docs/operations.md` for current job guidance.

## Purpose

Quick reference for the scripts in `app/jobs/`: what each one does, how to run it, and what changes before/after execution.

## How to Run Jobs

From repository root:

```bash
.\.venv\Scripts\Activate.ps1
python -m app.jobs.<job_module>
```

Example:

```bash
python -m app.jobs.run_phase2_extraction
```

## Job Matrix

| Job module | What it does | Run command |
|---|---|---|
| `run_phase2_extraction` | Processes eligible raw messages through extraction, triage, routing, event updates, and entity indexing. | `python -m app.jobs.run_phase2_extraction` |
| `run_deep_enrichment` | Processes deterministic `deep_enrich` candidates and stores narrow Pass B structured outputs. | `python -m app.jobs.run_deep_enrichment` |
| `run_digest` | Builds and publishes digest output from recent events and records publication. | `python -m app.jobs.run_digest` |
| `run_theme_batch` | Runs one deterministic theme batch window and persists run/evidence/assessment/card/brief rows. | `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily` |
| `test_openai_extract` | Runs a single extraction smoke test against OpenAI + schema validation (no DB writes). | `python -m app.jobs.test_openai_extract` |
| `clear_all_but_raw_messages` | Deletes derived pipeline tables while preserving `raw_messages`. | `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages` |
| `reset_dev_schema` | Drops and recreates all tables from SQLAlchemy models (destructive). | `python -m app.jobs.reset_dev_schema` |
| `adopt_stability_contracts` | Backfills replay/identity hashes, audits duplicate event identities, and optionally merges exact duplicates / applies unique indexes. | `python -m app.jobs.adopt_stability_contracts` |
| `adopt_theme_batch_schema` | Non-destructively ensures additive theme batch schema tables and indexes. | `python -m app.jobs.adopt_theme_batch_schema` |
| `adopt_structured_event_schema` | Non-destructively ensures additive structured-event tables/indexes and route column adoption. | `python -m app.jobs.adopt_structured_event_schema` |

## Before/After by Job

### `run_phase2_extraction`

- Before:
  - `raw_messages` contains ingested rows.
  - `message_processing_states` has `pending`/`failed`/expired lease rows.
  - Env requires `PHASE2_EXTRACTION_ENABLED=true` and `OPENAI_API_KEY`.
- After:
  - `extractions` inserted/updated for processed messages.
  - identical replay identity rows are reused without model call by default.
  - identical normalized text rows (same extractor/prompt/schema/canonicalizer contract) can reuse prior canonical extraction across different raw messages without model call.
  - `routing_decisions` persisted.
  - `events` and `event_messages` created/updated.
  - `event_tags` and `event_relations` synced per event.
  - deterministic `impact_score_breakdown` + `enrichment_route` persisted in extraction metadata.
  - `entity_mentions` inserted idempotently.
  - `message_processing_states` moved to `completed` or `failed`.

### `run_deep_enrichment`

- Before:
  - phase2 has produced `enrichment_candidates` with `enrichment_route`.
  - candidates marked `selected=true` and `enrichment_route=deep_enrich` exist.
- After:
  - `event_deep_enrichments` rows are inserted for newly processed shortlisted events.
  - reruns skip events already enriched (idempotent one-row-per-event behavior).

### `run_digest`

- Before:
  - `events` has recent rows inside `VIP_DIGEST_HOURS` window.
  - Telegram bot publish env vars are configured.
- After:
  - Canonical digest artifact is persisted before publish attempt.
  - Destination publish uses artifact identity (`input_hash`/`canonical_hash`) and per-destination status.
  - `published_posts` is updated with publish/skip/retry outcomes.

### `run_theme_batch`

- Before:
  - Event/extraction pipeline has produced events in target window.
  - Theme key is provided (`--theme energy_to_agri_inputs` for current POC).
- After:
  - `theme_runs` has one run status row.
  - `event_theme_evidence` contains/updates deterministic evidence matches.
  - `theme_opportunity_assessments` persists canonical internal assessments.
  - `thesis_cards` persists emitted/suppressed/draft statuses.
  - `theme_brief_artifacts` persists one brief row per run.

### `test_openai_extract`

- Before:
  - `PHASE2_EXTRACTION_ENABLED=true`.
  - `OPENAI_API_KEY` and model config are set.
- After:
  - Prints extractor/model/latency and validated JSON to console.
  - Does not write pipeline rows (`raw_messages`, `extractions`, `events`, etc.).

### `clear_all_but_raw_messages`

- Before:
  - You want to reprocess from existing raw history.
  - `CONFIRM_CLEAR_NON_RAW=true` is set.
- After:
  - Cleared tables: `event_messages`, `thesis_cards`, `theme_opportunity_assessments`, `theme_brief_artifacts`, `event_theme_evidence`, `theme_runs`, `published_posts`, `digest_artifacts`, `events`, `routing_decisions`, `extractions`, `message_processing_states`, `processing_locks`.
  - `raw_messages` remains unchanged.
  - On SQLite, ID sequences are reset where possible.

### `reset_dev_schema`

- Before:
  - You need a full schema reset in dev/test.
- After:
  - All tables are dropped and recreated from current models.
  - All data is removed, including `raw_messages`.
  - Current status: no runtime confirmation guard is enforced in this script.

### `adopt_stability_contracts`

- Before:
  - Existing DB may contain historical rows created before replay/event identity v2 contracts.
- After:
  - backfilled extraction/event identity hashes
  - duplicate identity groups audited (exact vs conflict)
  - optional exact duplicate merge (`--merge-exact`)
  - optional unique index apply (`--apply-unique-indexes`) once duplicates are cleaned

## Suggested Order

1. Start API and ingest messages.
2. Run `run_phase2_extraction`.
3. Run `run_digest`.
4. Use `clear_all_but_raw_messages` when iterating derived logic.
5. Use `reset_dev_schema` only for full destructive resets.

