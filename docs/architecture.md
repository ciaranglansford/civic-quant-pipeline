# Architecture

## System Shape

Civicquant is a modular monolith:
- one FastAPI app
- one shared SQL database (SQLite default, PostgreSQL compatible)
- separate background jobs for extraction, enrichment, digest, and theme batch processing

Entry point:
- `app/main.py` (`create_app`, router wiring, DB init in lifespan)

## Runtime Entry Points

| Component | Code path | Command |
|---|---|---|
| API | `app/main.py` | `uvicorn app.main:app --reload` |
| Listener | `listener/telegram_listener.py` | `python -m listener.telegram_listener` |
| Phase2 extraction | `app/jobs/run_phase2_extraction.py` | `python -m app.jobs.run_phase2_extraction` |
| Deep enrichment | `app/jobs/run_deep_enrichment.py` | `python -m app.jobs.run_deep_enrichment` |
| Digest | `app/jobs/run_digest.py` | `python -m app.jobs.run_digest` |
| Theme batch | `app/jobs/run_theme_batch.py` | `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily` |

## Module Ownership

- `app/routers/*`: HTTP adapters only.
- `app/workflows/phase2_pipeline.py`: phase2 orchestration (selection, lock, state transitions, cross-context sequencing).
- `app/workflows/deep_enrichment_pipeline.py`: deep enrichment lock + batch orchestration.
- `app/workflows/theme_batch_pipeline.py`: theme batch orchestration and lifecycle.
- `app/contexts/ingest/*`: source envelope mapping, normalization, raw persistence.
- `app/contexts/extraction/*`: prompt rendering, OpenAI extraction client, strict parsing/validation, canonicalization, replay/content reuse.
- `app/contexts/triage/*`: calibrated impact scoring, deterministic triage/routing decisioning, relatedness helpers.
- `app/contexts/events/*`: event matching, upsert, review flags, event-tag/relation sync.
- `app/contexts/entities/*`: entity mention indexing.
- `app/contexts/enrichment/*`: enrichment candidate selection and deep enrichment materialization.
- `app/contexts/feed/*`: feed query pagination/filtering.
- `app/digest/*`: canonical digest query/build/synthesis/render/artifact/publish semantics.
- `app/contexts/themes/*`: theme definitions, matching, event-theme evidence, evidence bundling.
- `app/contexts/opportunities/*`: assessment scoring, thesis cards, brief artifacts, enrichment providers for theme batch.

Compatibility shims:
- `app/services/digest_builder.py`
- `app/services/digest_query.py`
- `app/services/digest_runner.py`
- `app/services/telegram_publisher.py`

These shims delegate to `app/digest/*` and should not contain business logic.

## Deterministic vs LLM Responsibilities

Deterministic responsibilities:
- ingest idempotency and persistence
- extraction schema validation and canonicalization
- calibrated impact scoring and triage actioning
- event identity/upsert and structured facet sync
- digest event selection, pre-dedupe, synthesis validation, artifact identity, publish state updates
- theme evidence matching, bundling, scoring, gating, persistence

LLM responsibilities:
- phase2 extraction parsing (`OpenAiExtractionClient`)
- digest synthesis composition (`OpenAiDigestSynthesisClient`) when enabled

The code, not the model, remains authoritative for state transitions, IDs, dedupe, and publication safety.

## Domain Semantics

- Raw messages, extractions, events, and digest bullets are representations of reported claims.
- They are not factual verification outputs.
- Attribution and uncertainty language are preserved where possible.
