# Civicquant Intelligence Pipeline

Civicquant is a modular-monolith intelligence pipeline for wire-style bulletin streams. It captures reported claims, structures them, clusters them into evolving events, and produces scheduled digest and thematic outputs.

Truth model:
- events and digests are reported-claim representations, not confirmed facts
- attribution and uncertainty language should be preserved

## What This Repository Runs

- FastAPI backend (`app/main.py`)
- Telegram listener (`listener/telegram_listener.py`)
- Phase2 extraction/orchestration workflow (`app/workflows/phase2_pipeline.py`)
- Selective deep enrichment workflow (`app/workflows/deep_enrichment_pipeline.py`)
- Canonical digest workflow (`app/digest/*`)
- Deterministic theme batch workflow (`app/workflows/theme_batch_pipeline.py`)

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure `.env` (minimum for local API + phase2):
- `DATABASE_URL`
- `PHASE2_EXTRACTION_ENABLED=true`
- `OPENAI_API_KEY`
- optional listener/digest/theme settings

4. Start the API:

```bash
uvicorn app.main:app --reload
```

5. Run core jobs:

```bash
python -m app.jobs.run_phase2_extraction
python -m app.jobs.run_deep_enrichment
python -m app.jobs.run_digest
python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily
```

6. Optional listener:

```bash
python -m listener.telegram_listener
```

## Architecture At A Glance

`Ingest -> Normalize -> Extract (LLM + strict validation) -> Canonicalize + score + triage -> Event upsert -> Entity/theme evidence -> Digest/theme batch outputs`

Key boundaries:
- `app/contexts/*`: domain logic
- `app/workflows/*`: cross-context orchestration
- `app/digest/*`: canonical digest semantics and publishing
- `app/services/*`: digest compatibility shims only

## Documentation

Start here:
- `docs/README.md`

Canonical docs:
- `docs/architecture.md`
- `docs/system-flow.md`
- `docs/local-development.md`
- `docs/configuration.md`
- `docs/api.md`
- `docs/data-model.md`
- `docs/operations.md`
- `docs/troubleshooting.md`

Historical planning/audit artifacts are retained in `docs/05-audit/`, `docs/feed-api/`, `plans/`, and `user-stories/`.

