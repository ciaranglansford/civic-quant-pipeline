# Canonical Digest Pipeline

## Invariant

**No publish attempt occurs unless a canonical artifact has already been persisted.**

## Scope

This document describes the digest reporting architecture implemented for v1:
- Canonical digest generation is destination-agnostic.
- Canonical text rendering is deterministic.
- Destination publishing is adapter-based.
- Telegram is implemented.
- X is placeholder/deferred only.

## Implementation Home

- Digest implementation package: `app/digest/`
  - `types.py` - canonical digest structure
  - `query.py` - deterministic event selection
  - `builder.py` - canonical digest model generation
  - `renderer_text.py` - deterministic canonical plain-text rendering
  - `artifact_store.py` - canonical artifact persistence
  - `dedupe.py` - minimal per-destination dedupe checks
  - `orchestrator.py` - pipeline orchestration
  - `adapters/telegram.py` - Telegram publishing adapter
  - `adapters/x_placeholder.py` - deferred X placeholder
- Job entrypoint: `app/jobs/run_digest.py`

Transitional compatibility shims:
- `app/services/digest_query.py`
- `app/services/digest_builder.py`
- `app/services/digest_runner.py`
- `app/services/telegram_publisher.py`

## Schema Adoption Reality (Local/Dev)

- The repo currently has no migration framework.
- `create_all` does not alter existing tables/columns.
- Local/dev adoption step for this refactor:
  - `python -m app.jobs.reset_dev_schema`
- `app/jobs/reset_dev_schema.py` already exists and performs destructive drop/create.

## Deterministic Contract

- Window is frozen at run start in UTC with second precision.
- Inclusion rule:
  - include event iff `last_updated_at` in `[window_start_utc, window_end_utc)`.
- Digest meaning:
  - events created or materially updated during this window.
- Re-entry:
  - event can appear in later digest if updated into later window.
- Topic ordering:
  - alphabetical by normalized topic label.
- Item ordering:
  - `last_updated_at` descending, then `event_id` ascending.
- Canonical text:
  - no runtime-generated timestamps or volatile metadata.
  - if window metadata is present, it uses frozen window bounds only.
- No-interpretation behavior:
  - informational only, no investment advice.

## Artifact-First Flow

1. Freeze window.
2. Query events by deterministic rule.
3. Build canonical digest model.
4. Render canonical plain text.
5. Persist canonical artifact (`digest_artifacts`) and commit.
6. Only then publish through enabled adapters.
7. Record per-destination outcome rows in `published_posts`.

## Adapter Responsibilities

- Adapters are responsible for:
  - destination payload rendering from canonical inputs,
  - transport API interaction,
  - returning destination status metadata.
- Adapters are not responsible for:
  - event selection,
  - digest semantics,
  - canonical hashing policy.

### Telegram Presentation Boundary

- Canonical text artifact remains plain, deterministic, and destination-agnostic.
- Telegram adapter renders a Telegram-specific HTML payload from canonical digest inputs.
- Telegram presentation enhancements (title, compact metadata, top developments, section styling, footer) are adapter-only concerns.
- Top developments are selected deterministically from digest items using:
  - `last_updated_at` descending, then `event_id` ascending.
- Telegram payload hash is computed from the final Telegram-rendered payload and stored in `published_posts.content_hash`.

## Idempotency / Rerun Behavior

- Artifact identity is canonical hash of canonical text.
- Destination payload identity is payload hash.
- Rerun behavior per artifact+destination:
  - `published` -> skip.
  - `failed` -> retry.

## Deferred Follow-Up

- Real X publishing implementation.
- Full run/artifact/publication/attempt schema split.
- Advanced dedupe and retry policy tuning.
