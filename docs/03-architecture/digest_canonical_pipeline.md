# Canonical Digest Pipeline

> Legacy sectioned digest architecture note retained for context. Prefer `docs/system-flow.md` and `docs/operations.md` for current end-to-end behavior.

## Invariant

No publish attempt occurs unless a digest artifact has already been persisted and committed.

## Scope

This document covers architecture boundaries for the digest subsystem in `app/digest/`.

Current architecture is hybrid:
- deterministic event selection, coverage tracking, and publication state updates
- LLM-assisted synthesis for semantic merge and editorial composition

## Implementation Home

- `app/digest/query.py` - deterministic event selection
- `app/digest/builder.py` - source event modeling + deterministic pre-dedupe + deterministic fallback composition
- `app/digest/synthesizer.py` - LLM synthesis orchestration + strict validation + fallback routing
- `app/digest/renderer_text.py` - canonical text rendering
- `app/digest/artifact_store.py` - artifact persistence and deterministic input hashing
- `app/digest/orchestrator.py` - end-to-end pipeline orchestration
- `app/digest/adapters/*` - destination rendering/transport only

Transitional service shims remain in:
- `app/services/digest_query.py`
- `app/services/digest_builder.py`
- `app/services/digest_runner.py`

Additional transitional shim:
- `app/services/telegram_publisher.py`

Shim policy in this pass:
- thin delegation/re-export only
- no business logic
- explicit removal TODOs are tracked in shim module docstrings

## Canonical Semantics

Canonical digest semantics now include:
- `source_events` (selected source rows)
- `top_developments`
- `sections`
- `covered_event_ids`

Key rule:
- each rendered bullet carries explicit `source_event_ids`
- merged bullets can represent multiple source events
- successful publish marks all `covered_event_ids`

## Deterministic vs LLM Responsibilities

Deterministic:
- window freezing and event selection filters
- pre-dedupe by claim/fingerprint/normalized summary
- synthesis output validation
- artifact identity (`input_hash`) and rerun dedupe
- publication status writes and event published-flag updates

LLM:
- semantic same-story merging
- composition of top developments and topic bullets
- wording quality under truth-model constraints

## Adapter Boundary

Adapters are presentation/transport layers only.

Adapters must not decide:
- top-development selection
- dedupe semantics
- source coverage tracking

Adapters can decide:
- destination formatting (for example Telegram HTML)
- transport API retries/error mapping

## Artifact Identity and Idempotency

Digest artifacts use:
- `input_hash`: stable hash of selected source events + synthesis inputs
- `canonical_hash`: hash of rendered canonical text

Rerun behavior:
- existing `published` for artifact+destination -> skip
- existing `failed` for artifact+destination -> retry

Why `input_hash`:
- canonical prose can vary between synthesis retries
- source-input identity remains stable and deterministic

## Truth Model

Digest output remains a reported-claims briefing:
- does not assert external confirmation
- should preserve uncertainty markers from source material when available
- should not manufacture certainty

## Operational Note

The repository currently has no migration framework. Schema changes (for example `digest_artifacts.input_hash`) require local schema reset/recreate workflows in dev environments.

