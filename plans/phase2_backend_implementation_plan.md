# Phase2 Backend Implementation Plan (Story-Driven, Pipeline-Ordered)

## Summary
Implement the remaining backend stories in strict pipeline order, using docs + user stories as source of truth, and preserving wire-bulletin claim semantics (reported claim, not verified fact).
Already-implemented stories (BE-06..BE-10, INF/OPS baseline, typed extraction persistence) remain unchanged unless needed for extension.
This plan implements the missing/partial slices: BE-11, BE-12, BE-13, BE-14, BE-15, DB-03, BE-16, BE-17 plus required tests and targeted docs updates required by those stories.

## Stage 1 Calibration Pass (Implemented)
- Deterministic triage now treats model confidence/impact as bounded signals, not direct urgency truth.
- Score-band based routing calibration is applied without mutating stored raw extraction scores.
- Repetitive low-delta bursts are downgraded via deterministic novelty/material-change and burst-cap rules.
- Soft-related checks are used for triage downgrade context only; Stage 1 keeps exact event association unchanged.
- High-risk unattributed summaries are safety-rewritten in canonical payload only; raw validated payload remains untouched.
- Local domestic incident patterns are downgraded and forced evidence-required without taxonomy redesign.

## Stage 2 Deferred (Not in this pass)
- Prompt-level summary phrasing constraints (for example, prompt v3) if Stage 1 deterministic guardrails remain insufficient.
- Optional taxonomy refinements for domestic incident handling.
- Optional soft-related event association experiments with strict safety gates and measured rollback plan.

## Scope Lock (What will be implemented)
- In scope:
  - Deterministic wire normalization deepening.
  - Extraction semantic contract enforcement in prompt/validation/tests.
  - Deterministic canonicalization + deterministic triage actioning.
  - Event clustering refinements for repetitive/contradictory bulletins.
  - Entity indexing dataset layer with query helpers.
  - Deferred enrichment candidate hooks.
  - Reporting readiness checks (event-level gating).
  - Test coverage for the above.
- Out of scope:
  - External validation/corroboration execution.
  - Retrieval API endpoints.
  - New publishing channels.
  - Broad architecture refactors.

## Decisions Locked
1. Triage persistence: add explicit routing fields (`triage_action`, `triage_rules`) in `routing_decisions`.
2. Entity indexing model: single normalized table `entity_mentions`.
3. Deferred enrichment persistence: new table `enrichment_candidates`.
4. Schema workflow: MVP-safe deterministic reset/init workflow remains canonical for local/dev; schema bootstrap stays SQLAlchemy model-driven.
5. Prompt versioning: never edit `v1` in place; introduce `v2` and store prompt version per extraction.
6. Payload auditability: store raw validated extraction and canonicalized extraction separately.

## Storage and Data Integrity Rules
- Raw messages remain immutable source-of-record data and are never rewritten by downstream stages.
- Extraction auditability requires two persisted artifacts per extraction:
  - raw validated payload in `payload_json`
  - canonicalized payload in `canonical_payload_json` (or equivalent)
- Downstream deterministic triage, event clustering, and entity indexing consume canonicalized payload.
- Audit/replay workflows must always be able to trace back to the raw validated payload.

## Implementation Order

### 1) Baseline Audit + Story-to-Code Checklist (non-functional prep)
- Map each acceptance criterion for BE-11..BE-17/DB-03 to concrete file targets before edits.
- Produce internal checklist and execute sequentially.

### 2) Stage 2: BE-11 Wire-Bulletin Structural Normalization
- Files:
  - `app/services/normalization.py`
  - `app/routers/ingest.py` (verify unchanged integration point)
- Changes:
  - Expand deterministic normalization rules for:
    - leading markers (`BREAKING`, `ALERT`, siren emoji, leading `*`),
    - dateline wrappers/separators,
    - repeated punctuation/spacing artifacts,
    - safe source-suffix boilerplate removal.
  - Preserve attribution/uncertainty phrases exactly.
  - Keep behavior deterministic and side-effect free.
- DoD:
  - `raw_messages.normalized_text` reflects expanded deterministic cleanup without claim mutation.

### 3) Stage 3: BE-12 Literal Reported-Claim Semantics
- Files:
  - `app/prompts/extraction_agent_v1.txt` (unchanged)
  - `app/prompts/extraction_agent_v2.txt` (new)
  - `app/services/prompt_templates.py`
  - `app/services/extraction_validation.py`
  - `app/services/phase2_processing.py` (verify no truth-status derivation)
- Changes:
  - Keep `app/prompts/extraction_agent_v1.txt` unchanged for reproducibility.
  - Create `app/prompts/extraction_agent_v2.txt` for semantic-contract updates.
  - Update prompt selection path to use `v2`.
  - Persist `prompt_version` on every extraction row (if field exists, ensure always set; if missing, add it).
  - Validation/error pathways remain schema-strict without adding truth-adjudication fields.
  - Confirm persistence writes only extraction contract + telemetry, no derived “verified truth” fields.
- DoD:
  - Semantic contract is explicit in prompt/validation behavior and covered by tests.

### 4) Stage 4: BE-13 Deterministic Canonicalization
- Files:
  - `app/services/canonicalization.py` (new)
  - `app/services/phase2_processing.py`
  - `app/models.py` (if `canonical_payload_json` is added on `extractions`)
- Changes:
  - Add deterministic canonicalizer:
    - country aliases mapped to full country names in Title Case (for example, `United States`, `United Kingdom`),
    - ticker cleanup (uppercase/dedup/format),
    - org/person whitespace/case normalization,
    - source label normalization when rule-safe.
  - Lock canonical country format across:
    - `entities.countries`
    - `affected_countries_first_order`
    - `event_fingerprint` country component
    - `entity_mentions.entity_value` where `entity_type='country'`
  - Store raw validated LLM extraction separately from canonicalized extraction:
    - keep `payload_json` as raw validated extraction
    - store canonicalized output in `canonical_payload_json` (or equivalent)
  - Canonicalization must be deterministic and auditable.
  - Optional: record applied canonicalization rules in `metadata_json`, but do not rely on metadata alone.
- DoD:
  - Same input yields same canonicalized output; phase2 uses canonicalized extraction downstream without losing original validated output.

### 5) Stage 4: BE-14 Deterministic Triage + Promotion Actions
- Files:
  - `app/services/triage_engine.py` (new)
  - `app/services/routing_engine.py` (adapt to consume triage output)
  - `app/services/ingest_pipeline.py` (routing persistence extension)
  - `app/models.py` (`routing_decisions` schema extension)
- Changes:
  - Add deterministic triage action classifier: `archive|monitor|update|promote` + reason codes.
  - Rule-based mapping from canonicalized extraction + context.
  - Persist `triage_action` and `triage_rules` in `routing_decisions`.
  - Keep existing routing outputs compatible (`store_to`, `publish_priority`, `event_action`, `flags`).
- DoD:
  - Reproducible triage outputs; persisted action + rule IDs per row.

### 6) Stage 5: BE-15 Event Clustering Refinement
- Files:
  - `app/services/event_manager.py`
  - `app/services/phase2_processing.py` (context wiring)
- Changes:
  - Make precedence/update policy explicit in code for repetitive/paraphrase/contradictory updates.
  - Ensure matching fingerprint/window attaches to existing event.
  - Contradictory observations update summary/flags deterministically while preserving observation history via `event_messages`.
  - Preserve unique `(event_id, raw_message_id)` linkage rule.
- DoD:
  - Deterministic update behavior with no raw/extraction mutation.

### 7) Stage 6: DB-03 Entity Indexing Dataset Layer
- Files:
  - `app/models.py` (new `EntityMention`)
  - `app/services/entity_indexing.py` (new)
  - `app/services/phase2_processing.py` (populate on success)
- Table contract:
  - `entity_mentions`: `id`, `entity_type`, `entity_value`, `raw_message_id`, `event_id`, `topic`, `is_breaking`, `event_time`, `created_at`
- Indexes:
  - `(entity_type, entity_value, event_time)`
  - `(topic, event_time)`
  - `(is_breaking, event_time)`
  - uniqueness/idempotency key on `(raw_message_id, entity_type, entity_value)`
- Changes:
  - Deterministic extraction-to-index population for countries/orgs/people/tickers.
  - Query helper(s) for filter-ready retrieval patterns.
- DoD:
  - Entity links are inserted deterministically and idempotently during phase2.

### 8) Stage 7: BE-16 Deferred Enrichment Hooks
- Files:
  - `app/models.py` (new `EnrichmentCandidate`)
  - `app/services/enrichment_selection.py` (new)
  - `app/services/phase2_processing.py`
- Table contract:
  - `enrichment_candidates`: `id`, `event_id`, `triage_action`, `reason_codes` (JSON), `selected`, `created_at`
  - uniqueness on `(event_id)` for latest MVP selection semantics.
- Changes:
  - Deterministic selection hook from event-level signals.
  - Persist candidate decision + reasons; no external calls.
  - Non-blocking: failures here do not mutate raw ingest behavior.
- DoD:
  - High-signal events selected deterministically; low-signal events not selected.

### 9) Stage 8: BE-17 Reporting Readiness from Event-Level Data
- Files:
  - `app/services/digest_query.py`
  - `app/services/digest_runner.py`
  - `app/services/digest_builder.py` (minimal, if needed for degraded output messaging)
- Changes:
  - Add readiness gate before publish:
    - freshness window check,
    - required minimum event fields check (`summary`, `topic`, timing).
  - If not ready: skip or degrade gracefully with explicit logs.
  - Ensure reporting path remains event-level only (no raw text rendering).
- DoD:
  - Readiness behavior is deterministic and observable in logs.

### 10) Storage/Schema Application Workflow (MVP-safe)
- Files:
  - `app/jobs/reset_dev_schema.py` (verify table recreation includes new models)
  - `docs/04-operations/operations_and_scheduling.md` (only if command/verification updates required by stories)
- Changes:
  - Keep explicit confirm-flag guarded reset workflow as canonical local schema updater.
  - Validate `Base.metadata.create_all` covers all new tables/columns in dev.
- DoD:
  - Local developers can deterministically reset/init and run phase2 with new schema.

### 11) Tests (Required by Stories)
- New/updated tests:
  - `tests/test_normalization.py` (BE-11)
  - `tests/test_extraction_semantics.py` (BE-12)
  - `tests/test_canonicalization.py` (BE-13)
  - `tests/test_triage_engine.py` (BE-14)
  - `tests/test_event_manager_refinement.py` (BE-15)
  - `tests/test_entity_indexing.py` (DB-03)
  - `tests/test_enrichment_selection.py` (BE-16)
  - `tests/test_digest_readiness.py` (BE-17)
  - extend `tests/test_e2e_backend.py` for integrated phase2 path assertions.
- Required scenarios:
  - deterministic same-input/same-output guarantees,
  - no silent fallback to stub,
  - contradictory bulletin event updates without history loss,
  - idempotent reprocessing for indexing and clustering,
  - readiness skip/degraded reporting behavior.

### 12) Docs Updates (Only where stories require)
- Update only required semantic/runbook references:
  - `docs/03-interfaces/schemas_and_storage_model.md` (BE-12/DB-03/BE-16 contracts),
  - `docs/02-flows/phase2_extraction_flow.md` and `docs/02-flows/DATA_FLOW.md` (BE-14/BE-16/BE-17 flow points),
  - `plans/llm_usage_and_prompts.md` (BE-12 semantic consistency),
  - `docs/04-operations/operations_and_scheduling.md` (BE-17 readiness + DB-03 verification commands if needed).

## Important Public Interface / Type Changes
- DB model changes:
  - `routing_decisions`: add `triage_action` (string), `triage_rules` (JSON list).
  - `extractions`: add `canonical_payload_json` (JSON/JSONB) while keeping `payload_json` as raw validated payload.
  - add `entity_mentions` table + retrieval indexes.
  - add `enrichment_candidates` table.
- Service interfaces:
  - new deterministic services:
    - `canonicalization.canonicalize_extraction(...)`
    - `triage_engine.compute_triage_action(...)`
    - `entity_indexing.index_entities(...)`
    - `enrichment_selection.select_enrichment_candidate(...)`
- No new HTTP endpoints in this pass.

## Acceptance Test Scenarios
1. Normalization stability: wire marker/dateline cleanup is deterministic and meaning-preserving.
2. Claim semantics: uncertain attributed bulletin remains extracted as reported claim; no truth status inferred.
3. Canonicalization + triage: same payload always produces same canonical fields + triage action/rules.
4. Event refinement: paraphrase attaches existing event; contradiction updates event deterministically; history kept.
5. Entity indexing: countries/orgs/people/tickers indexed with idempotent inserts and time-window query support.
6. Enrichment hook: high-impact/breaking event marked candidate; low-impact not selected.
7. Reporting readiness: stale/incomplete datasets skip or degrade with explicit logs; ready datasets publish normally.
8. Pipeline e2e: ingest -> phase2 -> triage -> event -> indexing -> digest readiness works without raw mutation.

## Assumptions and Defaults
- Current repo architecture (FastAPI + SQLAlchemy + job scripts) remains unchanged.
- Raw messages remain immutable and are never updated by new logic.
- Schema updates are applied via deterministic local reset/init workflow for MVP development.
- No external enrichment execution is introduced; only selection hooks/persistence.
- Retrieval API endpoints remain out of scope; dataset readiness only.
