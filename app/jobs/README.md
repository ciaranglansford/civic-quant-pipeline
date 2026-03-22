# Jobs README

This folder contains operational scripts you run as Python modules from the repo root.

Ownership note:
- Jobs are entrypoints.
- Phase2 orchestration is implemented in `app/workflows/phase2_pipeline.py`.
- Digest/report semantics remain canonical in `app/digest/`.

## How to run

1. Open a shell in the repository root.
2. Ensure dependencies are installed: `pip install -r requirements.txt`.
3. Ensure your `.env` is configured.
4. Run jobs with `python -m app.jobs.<job_module>`.

## Jobs at a glance

| Job module | Command | What it does (1-liner) | Required env |
|---|---|---|---|
| `backfill_telegram_raw_messages` | `python -m app.jobs.backfill_telegram_raw_messages --limit 100` | Pulls the most recent Telegram messages and inserts them into `raw_messages` through the ingest pipeline. | `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_NAME`, `TG_SOURCE_CHANNEL`, `DATABASE_URL` |
| `run_phase2_extraction` | `python -m app.jobs.run_phase2_extraction` | Runs one phase2 extraction batch and writes extraction, triage, and event updates to DB. | `PHASE2_EXTRACTION_ENABLED=true`, `OPENAI_API_KEY`, `DATABASE_URL` |
| `run_deep_enrichment` | `python -m app.jobs.run_deep_enrichment` | Runs one selective Pass B deep enrichment batch for deterministic `deep_enrich` candidates. | `DATABASE_URL` |
| `run_digest` | `python -m app.jobs.run_digest` | Builds/publishes the digest from current event data. | `DATABASE_URL` (and digest delivery vars if publishing) |
| `run_theme_batch` | `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily` | Runs one deterministic thematic batch window and persists run/evidence/assessment/card/brief artifacts. | `DATABASE_URL` |
| `run_opportunity_memo` | `python -m app.jobs.run_opportunity_memo --start <iso> --end <iso> [--topic <topic>]` | Runs one on-demand single-topic opportunity memo workflow and records persistence + delivery outcome. | `DATABASE_URL`, `OPENAI_API_KEY` (default provider/writer path) |
| `test_openai_extract` | `python -m app.jobs.test_openai_extract` | Smoke-tests the OpenAI extraction call and prints validated JSON output. | `PHASE2_EXTRACTION_ENABLED=true`, `OPENAI_API_KEY` |
| `inspect_pipeline` | `python -m app.jobs.inspect_pipeline` | Prints a recent end-to-end pipeline overview (raw -> extraction -> routing -> event). | `DATABASE_URL` |
| `clear_all_but_raw_messages` | `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages` | Deletes all derived pipeline tables while preserving `raw_messages`. | `DATABASE_URL`, `CONFIRM_CLEAR_NON_RAW=true` |
| `reset_dev_schema` | `python -m app.jobs.reset_dev_schema` | Drops and recreates the full DB schema for a clean dev reset. | `DATABASE_URL` |
| `adopt_stability_contracts` | `python -m app.jobs.adopt_stability_contracts` | Backfills replay/identity hashes, audits duplicate event identities, and can optionally merge exact duplicates/apply unique indexes. | `DATABASE_URL` |
| `adopt_theme_batch_schema` | `python -m app.jobs.adopt_theme_batch_schema` | Non-destructively creates/ensures additive theme-batch tables/indexes. | `DATABASE_URL` |
| `adopt_structured_event_schema` | `python -m app.jobs.adopt_structured_event_schema` | Non-destructively creates/ensures additive structured-event tables/indexes and route-column adoption. | `DATABASE_URL` |
| `adopt_opportunity_memo_schema` | `python -m app.jobs.adopt_opportunity_memo_schema` | Non-destructively creates/ensures additive opportunity-memo tables/indexes. | `DATABASE_URL` |

## Job-specific usage

### `inspect_pipeline`

Overview mode (latest rows):

```bash
python -m app.jobs.inspect_pipeline --limit 20
```

Detail mode (single raw message id):

```bash
python -m app.jobs.inspect_pipeline --detail 123
```

### `backfill_telegram_raw_messages`

Backfill the latest 250 messages from your configured source channel:

```bash
python -m app.jobs.backfill_telegram_raw_messages --limit 250
```

Override channel at runtime (useful for ad-hoc recovery against another source):

```bash
python -m app.jobs.backfill_telegram_raw_messages --limit 250 --channel @your_channel_name
```

### `run_opportunity_memo`

Auto-topic path:

```bash
python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z
```

Manual topic override:

```bash
python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z --topic natural_gas
```

Possible run states:
- `no_topic_found`
- `validation_failed`
- `completed`
- `delivery_failed`

### `clear_all_but_raw_messages`

PowerShell:

```powershell
$env:CONFIRM_CLEAR_NON_RAW='true'; python -m app.jobs.clear_all_but_raw_messages
```

Bash:

```bash
CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages
```

### `reset_dev_schema`

```bash
python -m app.jobs.reset_dev_schema
```

Warning: this is destructive and currently executes without a runtime confirmation guard in code.

### `adopt_stability_contracts`

Audit/backfill only:

```bash
python -m app.jobs.adopt_stability_contracts
```

Dry-run (no writes committed):

```bash
python -m app.jobs.adopt_stability_contracts --dry-run
```

Merge exact duplicate identity groups and apply unique indexes after cleanup:

```bash
python -m app.jobs.adopt_stability_contracts --merge-exact --apply-unique-indexes
```

## Practical run order (local)

1. `python -m app.jobs.run_phase2_extraction`
2. `python -m app.jobs.run_deep_enrichment`
3. `python -m app.jobs.inspect_pipeline --limit 20`
4. `python -m app.jobs.run_digest`
5. `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily`
6. `python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z`

## Phase2 replay/content reuse knobs

- `PHASE2_FORCE_REPROCESS` (default `false`): force model call even when replay/content reuse candidates exist.
- `PHASE2_CONTENT_REUSE_ENABLED` (default `true`): allow cross-message canonical extraction reuse when normalized text + extractor contract match.
- `PHASE2_CONTENT_REUSE_WINDOW_HOURS` (default `6`): only reuse prior extractions created within this window (set `0` or negative to disable window bound).

## Troubleshooting

- If phase2 jobs fail immediately, confirm `PHASE2_EXTRACTION_ENABLED=true` and `OPENAI_API_KEY` are set.
- If DB-related jobs fail, confirm `DATABASE_URL` points to the expected database.
- If job imports fail, run from the repository root.

