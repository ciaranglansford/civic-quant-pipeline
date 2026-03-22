# Troubleshooting

## Phase2 Admin Trigger Returns 401

Checks:
- `PHASE2_ADMIN_TOKEN` is set in environment.
- request includes header `x-admin-token` with exact token value.

If `PHASE2_ADMIN_TOKEN` is unset, `/admin/process/phase2-extractions` and admin structured query endpoints always reject.

## Phase2 Job Fails Immediately

Checks:
- `PHASE2_EXTRACTION_ENABLED=true`
- `OPENAI_API_KEY` is set
- DB is reachable (`DATABASE_URL`)

## Messages Ingest but Never Process

Checks:
- `message_processing_states.status` and `lease_expires_at`
- `processing_locks` row for `phase2_extraction`
- phase2 logs for lock contention (`phase2_lock_busy`)

## Digest Run Completes but Nothing Publishes

Checks:
- event selection window has eligible events (`last_updated_at` in digest window, impact > 25)
- destination is enabled (`TG_BOT_TOKEN` and `TG_VIP_CHAT_ID` for `vip_telegram`)
- destination may be skipped as already published for same artifact

## Digest Synthesis Seems Ignored

Checks:
- `DIGEST_LLM_ENABLED=true`
- model/key configured (`DIGEST_OPENAI_MODEL` or `OPENAI_MODEL`, plus `OPENAI_API_KEY`)
- logs may show fallback reason from `digest.synthesizer`

Even when synthesis fails, digest still returns deterministic fallback output.

## Theme Run Fails or Produces No Cards

Checks:
- `theme_key` exists (`GET /admin/themes`)
- requested cadence is supported by that theme
- run window contains matching evidence
- assessment/card gate thresholds may suppress card emission

Inspect:
- `theme_runs.error_message`
- `theme_opportunity_assessments`
- `thesis_cards.status` and `suppression_reason`

## Deep Enrichment Produces No Rows

Checks:
- `DEEP_ENRICHMENT_ENABLED=true`
- `enrichment_candidates` has rows where `selected=true` and `enrichment_route='deep_enrich'`
- no existing `event_deep_enrichments` rows for same events

## Need Safe Reprocessing

Use:

```bash
CONFIRM_CLEAR_NON_RAW=true python -m app.jobs.clear_all_but_raw_messages
```

Then rerun phase2/deep enrichment/digest/theme batch as needed.
