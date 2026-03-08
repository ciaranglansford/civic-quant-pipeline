# User Story Drift Review (Phase 1 -> Phase 3 Iteration)

Purpose: compare documented intent vs implemented behavior and highlight likely story drift or missing draft stories.

Date reviewed: 2026-03-06
Evidence sources: `user-stories/`, `app/`, `docs/`, `plans/`, `tests/` + `pytest -q` (27 passed)

## Phase 1 - Foundation (MVP capture -> structure -> event -> publish)

### Aims from stories
- Capture Telegram bulletins reliably and idempotently.
- Preserve immutable raw source records.
- Normalize text deterministically for stable extraction/dedup.
- Extract structured fields, route deterministically, cluster into events.
- Publish periodic digest with auditability and operational logs.

### Implemented
- Listener + backend ingest path with idempotent raw writes exists.
- `raw_messages` has uniqueness constraint and `normalized_text` persistence.
- Extraction/routing/event pipeline exists with `extractions`, `routing_decisions`, `events`, `event_messages`.
- Digest generation/publish persistence exists via `published_posts`.
- Core observability logs and tests exist.

### Drift / follow-up draft candidates
- Story-level docs describe a Phase 1 stub extractor, but runtime is now OpenAI Phase2-first extraction for processing jobs.
- Consider drafting a “Phase 1 historical contract vs current operational path” reconciliation story, to avoid ambiguity for new contributors.

## Phase 2 - Core Scheduled Processing Build (early + middle Phase 2 stories)

Scope basis: BE-06..OPS-04 and BE-11..BE-17 (+ DB-03).

### Aims from stories
- Add scheduled extraction orchestration with locking, retries, strict validation, and traceability.
- Move to deterministic post-processing: canonicalization, triage actions, event refinement, entity indexing.
- Add runbooks and stage verification workflow.
- Prepare deferred enrichment hooks and reporting-readiness gates.

### Implemented
- Implemented strongly: BE-06, DB-01, BE-07, INF-01, INF-02, BE-08, DB-02, BE-09, OPS-01, OPS-02, BE-10.
- Implemented strongly: BE-11, BE-12, BE-13, BE-14, BE-15, DB-03.
- Implemented partially: OPS-03 (logs exist, but not all requested stable keys/metric surfaces are explicit).
- Implemented partially: OPS-04 (runbook exists and is useful; calibration verification detail is not fully threshold-driven).
- Not implemented yet: BE-16 deferred enrichment hooks (no `enrichment_selection` service/table).
- Not implemented yet: BE-17 reporting readiness gate (digest runs, but no explicit freshness/completeness gate with skip/degrade policy in code).

### Drift / uncreated-story draft candidates
- Draft: “Deferred enrichment candidate persistence and selector model” (explicitly replacing BE-16 gap).
- Draft: “Digest readiness gating and degraded-mode behavior” (explicitly replacing BE-17 gap).
- Draft: “OPS-03 observability completion: stable run/message keys + machine-readable counters.”

## Phase 3 - Iteration & Calibration Pass (late Phase 2 stories as iterative phase)

Scope basis: BE-18..OPS-05.

### What was iterated
- Triage calibration moved from raw-score interpretation toward deterministic score bands and novelty context.
- Soft-related repetition handling and burst downgrades added.
- High-risk unattributed summary safety rewrites added in canonical payload only.
- Local domestic incident downgrade/evidence override added.

### Implemented
- Implemented strongly: BE-18 (score/confidence bands, novelty/material-change rules, raw score preservation).
- Implemented strongly: BE-19 (soft-related used for calibration while exact event association remains authoritative).
- Implemented strongly: BE-20 (high-risk attribution rewrite in canonical payload only).
- Implemented strongly: BE-21 (local incident urgency cap + evidence-required routing override).
- Implemented partially: BE-22 (burst suppression exists, but story-specific source/topic window-key throttle + explicit rule IDs are not fully present).
- Implemented partially: BE-23 (pronoun rewrite exists; requested unsafe-context grammatical guardrail + explicit skip rule IDs not fully evident).
- Not implemented yet: BE-24 quality scorecard/threshold checks workflow.
- Not implemented yet: OPS-05 calibration regression runbook with threshold-based pass/fail and escalation flow.

### Drift / uncreated-story draft candidates
- Draft: “Promote-throttle v2 with `(topic, source_claimed, 15m bucket)` key and rule IDs from BE-22.”
- Draft: “Pronoun rewrite safe-context classifier + skip-rule telemetry from BE-23.”
- Draft: “Operational quality scorecard script + thresholds + fixture dataset from BE-24.”
- Draft: “Calibration regression runbook with SQL checks, pass/fail thresholds, escalation steps from OPS-05.”

## Suggested Comparison Checklist (for your docs)

Use these columns per story ID:
- `Intended outcome`
- `Implemented evidence (file/test/doc)`
- `Status: implemented | partial | missing`
- `Drift note`
- `Candidate follow-up story`

Priority gaps to reconcile first:
1. BE-16
2. BE-17
3. BE-24
4. OPS-05
5. BE-22/BE-23 completion details
