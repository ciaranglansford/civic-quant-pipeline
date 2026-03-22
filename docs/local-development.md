# Local Development

## Prerequisites

- Python environment with `pip`
- Access to `.env` configuration
- Optional: Telegram credentials if running listener/backfill

Install dependencies:

```bash
pip install -r requirements.txt
```

## Recommended Startup Order

1. Start API

```bash
uvicorn app.main:app --reload
```

2. Ingest data
- Option A: run listener

```bash
python -m listener.telegram_listener
```

- Option B: post directly to `/ingest/source` or `/ingest/telegram`.

3. Run phase2 extraction

```bash
python -m app.jobs.run_phase2_extraction
```

4. Run deep enrichment (optional)

```bash
python -m app.jobs.run_deep_enrichment
```

5. Run digest

```bash
python -m app.jobs.run_digest
```

6. Run theme batch

```bash
python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily
```

## Useful Dev Jobs

- Inspect recent pipeline rows:

```bash
python -m app.jobs.inspect_pipeline --limit 20
```

- Inspect one raw message lineage:

```bash
python -m app.jobs.inspect_pipeline --detail 123
```

- Backfill recent Telegram messages through ingest pipeline:

```bash
python -m app.jobs.backfill_telegram_raw_messages --limit 200
```

## Manual Admin Trigger

`POST /admin/process/phase2-extractions` requires:
- `PHASE2_ADMIN_TOKEN` configured
- header `x-admin-token` matching that value

Example:

```bash
curl -X POST "http://127.0.0.1:8000/admin/process/phase2-extractions?force_reprocess=false" -H "x-admin-token: YOUR_PHASE2_ADMIN_TOKEN"
```

## Tests

Run all tests:

```bash
pytest -q
```

Targeted suites:

```bash
pytest -q tests/test_e2e_backend.py
pytest -q tests/test_digest_pipeline.py
pytest -q tests/test_theme_batch_workflow.py
pytest -q tests/test_feed_api.py
```

## Reset and Reprocess

Clear derived tables but keep raw ingest history:

```bash
CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages
```

Full destructive schema reset:

```bash
python -m app.jobs.reset_dev_schema
```
