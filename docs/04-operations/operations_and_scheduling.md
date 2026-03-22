## Operations and Scheduling

> Legacy sectioned runbook retained for context. Prefer `docs/operations.md`, `docs/local-development.md`, and `docs/troubleshooting.md` for current operational guidance.

### Purpose

Primary local runbook for executing the wire-bulletin pipeline end-to-end and validating stage outputs.

## Runtime Components

- Backend API: `uvicorn app.main:app`
- Listener (capture): `python -m listener.telegram_listener`
- Phase2 extraction: `python -m app.jobs.run_phase2_extraction`
- Reporting digest (canonical pipeline): `python -m app.jobs.run_digest`
- Theme batch thesis POC: `python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily`
- Opportunity memo (on-demand): `python -m app.jobs.run_opportunity_memo --start <iso> --end <iso> [--topic <topic>]`

## Digest Pipeline Invariant

**No publish attempt occurs unless a canonical artifact has already been persisted.**

Implementation ownership:
- Canonical digest pipeline modules live in `app/digest/`.
- Job entrypoint remains `app/jobs/run_digest.py`.
- Legacy `app/services/digest_*` and `app/services/telegram_publisher.py` are transitional shims.

Digest composition details:
- deterministic selection and pre-dedupe happen before synthesis
- LLM synthesis is optional and guarded by strict validation
- deterministic fallback is used on disabled/invalid/error cases

## Opportunity Memo v1 Invariants

- CLI-first on-demand workflow (no new HTTP endpoint in v1).
- One run produces at most one memo for one topic.
- Internal memo input is derived from event-layer data only (not `raw_messages`).
- Deterministic topic mapping precedence is fixed:
  - `event_tags`
  - `event_relations`
  - latest extraction canonical payload
  - no match
- Memo writer evidence is limited to:
  - deterministic internal event evidence
  - normalized external evidence sources
- Memo artifact persistence occurs before Telegram delivery attempt.

## Schema Adoption (Digest Refactor)

- This repository currently has no migration framework.
- `Base.metadata.create_all(...)` creates missing tables but does not alter existing tables/columns.
- To adopt the digest schema changes on existing local/dev databases, reset/recreate schema:
  - `python -m app.jobs.reset_dev_schema`
- This reset job already exists and is destructive (`drop_all` + `create_all`).
- Current status: `reset_dev_schema` does not enforce a runtime env-confirmation guard; treat it as a dangerous manual command.

## Schema Adoption (Theme Batch Additions)

- Theme batch schema is additive and non-destructive.
- Adoption command:
  - `python -m app.jobs.adopt_theme_batch_schema`
- This command ensures new tables/indexes exist:
  - `theme_runs`
  - `event_theme_evidence`
  - `theme_opportunity_assessments`
  - `thesis_cards`
  - `theme_brief_artifacts`
- Rollback approach:
  - disable theme batch job/admin endpoints,
  - optionally clear/drop only theme tables,
  - existing ingest/extraction/triage/event/digest flows remain unchanged.

## Schema Adoption (Opportunity Memo v1 Additions)

- Opportunity memo schema is additive and non-destructive.
- Adoption command:
  - `python -m app.jobs.adopt_opportunity_memo_schema`
- This command ensures tables exist:
  - `opportunity_memo_runs`
  - `opportunity_memo_artifacts`
  - `opportunity_memo_input_events`
  - `opportunity_memo_external_sources`
  - `opportunity_memo_deliveries`

## Developer Run Sequence (Local)

1. Environment + dependencies
- Ensure Python environment is active.
- Install dependencies:
  - `pip install -r requirements.txt`
- Configure `.env` for DB, listener, phase2 extraction, and digest publishing as needed.

2. Start backend (Stages 1-2 entrypoint)
- Command:
  - `uvicorn app.main:app --reload`
- Expected outputs:
  - API responds on `/health`
  - Ingest endpoints available: `/ingest/telegram` and `/ingest/source`
  - DB tables available

3. Start listener (optional; Stage 1 capture source)
- Command:
  - `python -m listener.telegram_listener`
- Expected outputs:
  - Poll loop logs
  - New ingest payload posts
  - New `raw_messages` rows

4. Run extraction batch (Stages 3-5)
- Command:
  - `python -m app.jobs.run_phase2_extraction`
- Expected outputs:
  - extractor selection log
  - processing summary log
  - updates in `extractions`, `routing_decisions`, `events`, `event_messages`, `enrichment_candidates`

5. Run digest/report (Stage 8)
- Command:
  - `python -m app.jobs.run_digest`
- Expected outputs:
  - canonical artifact persisted in `digest_artifacts`
  - Telegram adapter builds destination-specific formatted payload (HTML) from canonical digest
  - per-destination publish outcomes in `published_posts`
  - digest publish/skip/retry logs per destination

6. Run opportunity memo (on-demand)
- Command:
  - `python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z`
  - optional manual topic override:
    - `python -m app.jobs.run_opportunity_memo --start ... --end ... --topic natural_gas`
- Expected outputs:
  - either clean no-op status `no_topic_found` with no publish attempt
  - or one persisted memo artifact and one Telegram delivery attempt with recorded outcome

7. Validation checks
- Verify stage outputs in DB:
  - Stage 1: `raw_messages`
  - Stage 3: `extractions`
  - Stage 4: `routing_decisions`
  - Stage 5: `events`, `event_messages`
  - Stage 8: `digest_artifacts`, `published_posts`
  - Opportunity memo: `opportunity_memo_runs`, `opportunity_memo_artifacts`, `opportunity_memo_input_events`, `opportunity_memo_external_sources`, `opportunity_memo_deliveries`
  - Theme batch: `theme_runs`, `event_theme_evidence`, `theme_opportunity_assessments`, `thesis_cards`, `theme_brief_artifacts`

## When to Run What

- Run listener when validating capture behavior against live/burst bulletin feeds.
- Run phase2 extraction when validating claim extraction, deterministic triage, and event clustering.
- Run digest when validating event-level reporting outputs.
- Run opportunity memo for on-demand single-topic client memo generation from a custom window.

## Data Lifecycle + Reprocess Safety

- Raw data (`raw_messages`) is immutable source-of-record.
- Derived data (`extractions`, `routing_decisions`, `events`, `event_messages`, `digest_artifacts`, `published_posts`, `opportunity_memo_*`, processing state) is reprocessable.

### Reprocess Commands

- Preserve raw, clear derived:
  - `CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages`
- Full dev schema reset (destructive):
  - `python -m app.jobs.reset_dev_schema`

Use preserve-raw reprocess for prompt/routing/event-logic iteration. Use full reset for schema-level resets.

## Scheduling

### Phase2 Extraction Cadence
- Recommended: every 10 minutes
- Example:
  - `*/10 * * * * python -m app.jobs.run_phase2_extraction`

### Digest Reporting Cadence
- Recommended: every 4 hours (or `VIP_DIGEST_HOURS`)
- Example:
  - `0 */4 * * * python -m app.jobs.run_digest`

### Theme Batch Cadence
- Suggested initial cadence:
  - daily: once per day
  - weekly: once per week
- Example:
  - `0 6 * * * python -m app.jobs.run_theme_batch --theme energy_to_agri_inputs --cadence daily`

### Opportunity Memo Cadence
- On-demand only in v1.
- No default scheduler entry is recommended.

### Digest Rerun / Idempotency Behavior
- Canonical artifact is persisted before destination publish attempts.
- Canonical digest semantics (top developments, sections, coverage IDs) are decided before adapter rendering.
- Adapter-specific payload formatting does not alter canonical coverage semantics.
- Artifact identity uses deterministic `input_hash` from source inputs and synthesis settings, with canonical hash fallback.
- If a destination already has `published` status for an artifact, rerun skips that destination.
- If a destination has `failed` status for an artifact, rerun retries that destination.
- Telegram is implemented now via adapter.
- X adapter is placeholder/deferred only and is disabled by default.

## Digest Synthesis Runtime Flags

- `DIGEST_LLM_ENABLED`
- `DIGEST_OPENAI_MODEL`
- `DIGEST_OPENAI_TIMEOUT_SECONDS`
- `DIGEST_OPENAI_MAX_RETRIES`
- `DIGEST_TOP_DEVELOPMENTS_LIMIT`
- `DIGEST_SECTION_BULLET_LIMIT`

## Targeted Test Commands

- Full suite:
  - `pytest -q`
- Extraction client tests:
  - `pytest -q tests/test_extraction_llm_client.py`
- Pipeline/e2e tests:
  - `pytest -q tests/test_e2e_backend.py`

## Expected Extraction Logs and Side Effects

### Key logs
- `phase2_config phase2_extraction_enabled=<bool> openai_api_key_present=<bool> openai_model=<value>`
- `Using extractor: extract-and-score-openai-v1`
- `phase2_run_done ... selected=<n> processed=<n> completed=<n> failed=<n> skipped=<n>` 
- `phase2_score_distribution ... count=<n> p95=<v> p99=<v> pct_gt_40=<v> pct_gt_60=<v> pct_gte_80=<v>`

### Key DB side effects
- `extractions`: typed extraction fields + `payload_json` + `metadata_json`
- `routing_decisions`: deterministic triage output
- `enrichment_candidates`: deterministic candidate decisions + novelty state
- `events`/`event_messages`: event cluster updates


## Calibrated Score Monitoring

Run after phase2 batches to detect prompt drift or calibration regressions.

### Required metrics
- p95 calibrated score
- p99 calibrated score
- percentage of events with calibrated score > 40
- percentage of events with calibrated score > 60
- percentage of events with calibrated score >= 80

### Example SQL checks
- `SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY impact_score) AS p95, percentile_cont(0.99) WITHIN GROUP (ORDER BY impact_score) AS p99 FROM extractions WHERE impact_score IS NOT NULL;`
- `SELECT 100.0 * AVG(CASE WHEN impact_score > 40 THEN 1 ELSE 0 END) AS pct_gt_40, 100.0 * AVG(CASE WHEN impact_score > 60 THEN 1 ELSE 0 END) AS pct_gt_60, 100.0 * AVG(CASE WHEN impact_score >= 80 THEN 1 ELSE 0 END) AS pct_gte_80 FROM extractions WHERE impact_score IS NOT NULL;`

### Debugging workflow
- Inspect `extractions.metadata_json->impact_scoring` for `rules_fired` and `score_breakdown`.
- Verify high scores have shock flags + transmission criteria met.
- Verify local/non-market incidents remain capped by deterministic rules.
## Troubleshooting: Repetitive or Contradictory Bulletins

- Repetition is expected in wire feeds; validate event clustering behavior, not one-message-one-event assumptions.
- Contradictory bulletins should appear as additional observations and may update existing event clusters.
- Inspect progression across `raw_messages` -> `extractions` -> `events/event_messages`.

## Troubleshooting: OpenAI Extraction Not Being Used

1. Confirm extraction job logs show `extract-and-score-openai-v1`.
2. Confirm phase2 env values (`PHASE2_EXTRACTION_ENABLED`, API key presence).
3. Inspect latest `extractions` rows for `extractor_name`, `payload_json`, and `metadata_json`.



