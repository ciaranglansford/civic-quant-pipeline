# Digest Pipeline (Hybrid Deterministic + LLM)

> Legacy deep-dive retained for context. Prefer `docs/system-flow.md`, `docs/operations.md`, and `docs/api.md` for current primary guidance.

## Purpose

This document describes the current digest implementation in `app/digest/` after the synthesis refactor.

The digest pipeline is intentionally hybrid:
- deterministic for selection, state transitions, and safety constraints
- LLM-assisted for semantic merge and editorial composition quality

## End-to-End Data Flow

1. Query candidate events
- `app/digest/query.py:get_events_for_window`
- deterministic filters:
  - window: `last_updated_at in [start, end)`
  - impact: `impact_score > 25.0` in orchestrator
  - destination publication-eligibility filter for known destinations

2. Build source digest events
- `app/digest/builder.py:build_source_digest_events`
- maps `Event` rows to canonical `SourceDigestEvent` values

3. Deterministic pre-dedupe / pre-group
- `app/digest/builder.py:pre_dedupe_source_events`
- groups obvious duplicates within topic using:
  - `claim_hash`
  - `event_fingerprint`
  - normalized summary text
- output is `SourceEventGroup` with `source_event_ids` coverage

4. Synthesis step
- `app/digest/synthesizer.py:synthesize_digest`
- if enabled and configured, calls LLM with structured candidates
- validates strict JSON output and semantic constraints
- on disabled/invalid/error, falls back to deterministic builder

5. Canonical rendering
- `app/digest/renderer_text.py:render_canonical_text`
- renders from `CanonicalDigest` only

6. Artifact persistence
- `app/digest/artifact_store.py:get_or_create_artifact`
- dedupe key:
  - primary: deterministic `input_hash` (from selected source events + synthesis inputs)
  - fallback: `canonical_hash` of rendered text

7. Publish + state updates
- `app/digest/orchestrator.py:run_digest`
- publish via adapter payload rendering
- on success, mark all `covered_event_ids` published for destination

## Canonical Data Structures

Defined in `app/digest/types.py`.

### `SourceDigestEvent`

Represents one selected source event (pre-merge):
- `event_id`
- `topic_raw`
- `topic_label`
- `summary_1_sentence`
- `impact_score`
- `last_updated_at`
- `event_fingerprint`
- `claim_hash`

### `DigestBullet`

Represents one rendered bullet:
- `text`
- `topic_label` (`None` for top developments)
- `source_event_ids`

`source_event_ids` is the critical mapping back to underlying event rows. One bullet may cover multiple source events.

### `TopicSection`

Represents one section in the digest:
- `topic_label`
- `bullets`
- `covered_event_ids`

`covered_event_ids` is the union of section bullet source IDs.

### `CanonicalDigest`

Source-of-truth object for rendering and publication:
- `window`
- `source_events`
- `top_developments`
- `sections`
- `covered_event_ids`

`covered_event_ids` drives publication state marking.

## Deduplication Strategy

### Layer 1: Deterministic pre-dedupe

Implemented in builder before LLM synthesis:
- normalizes summaries for matching (casefold, whitespace collapse, punctuation stripping)
- groups obvious duplicates by claim/fingerprint/summary identity keys
- produces stable candidate groups with merged `source_event_ids`

Why:
- remove trivial duplication in code
- reduce prompt noise and token waste
- make behavior testable and reproducible

### Layer 2: LLM semantic merge

LLM can merge same-story groups beyond exact-key equality.
- output bullets include merged `source_event_ids`
- validator enforces no ID reuse across bullets

Why:
- deterministic keys cannot capture all paraphrase-level sameness
- synthesis stage can resolve semantic overlap into concise briefing bullets

## Top Developments Logic

Top developments are no longer "most recent N" in adapters.

Current behavior:
- canonical digest stores explicit `top_developments`
- section bullets must not reuse top-development IDs
- fallback builder picks top groups deterministically from impact + recency ordering
- LLM path can choose prominence semantically, but IDs are still validated deterministically

## Synthesis Contract and Validation

Expected LLM JSON shape:
- `top_developments: list[{text, source_event_ids}]`
- `sections: list[{topic_label, bullets: list[{text, source_event_ids}]}]`
- `excluded_event_ids: optional list[int]`

Validator in `synthesizer.py` enforces:
- referenced IDs must exist in selected source set
- each source ID appears at most once across all bullets
- top/section coverage is disjoint by ID
- topics normalize to supported labels
- bullet text cannot be empty/whitespace
- duplicate bullet text normalization is collapsed or rejected (cross-location conflicts rejected)
- all source IDs must be accounted for by bullets or `excluded_event_ids`

On any validation/provider/template error:
- synthesis falls back to deterministic digest composition

## Deterministic Fallback Builder

`builder.py:build_deterministic_digest`:
- composes digest from deterministic pre-dedupe groups
- chooses top developments by impact + recency
- excludes top-covered IDs from sections
- preserves `source_event_ids` mapping for merged groups
- computes final `covered_event_ids`

## Rendering and Adapter Boundaries

Canonical object is the only semantic source of truth.

- `renderer_text.py` renders canonical plain text
- adapters (for example Telegram) only format and transport
- adapters do not decide top developments or dedupe semantics

## Publication and Coverage Semantics

- artifact persistence happens before publish attempt
- destination reruns skip already published artifact+destination rows
- successful publish marks `covered_event_ids` on `events`
- merged bullets still mark all underlying source event IDs

## Design Principles

- LLM for meaning, code for state
- never delegate state transitions to model output
- keep ID-level accounting deterministic and auditable
- digest is a synthesized interpretation layer, not a raw replay

## Notes / TODOs

- There is currently no migration framework in-repo; schema evolution (for example `digest_artifacts.input_hash`) requires local reset/recreate workflows in dev environments.
