# Civicquant Documentation Overview

> Legacy sectioned overview snapshot. Prefer the canonical docs in `docs/README.md` (`architecture.md`, `system-flow.md`, `api.md`, and related root docs pages).

## Purpose

This section explains what the system is, what is implemented now, and what the target architecture is intended to become.

## System Framing

Civicquant processes Telegram wire-bulletin feeds (headline/ticker style), not general chat conversation streams.

Input characteristics:
- short, urgent, source-attributed updates,
- repetitive and incremental observations,
- occasional contradictions,
- reported claims that may not yet be confirmed.

## Current Implementation

- Poll-based listener reads messages from one configured Telegram source and forwards to backend ingest.
- Ingest persists immutable `raw_messages` with idempotency by source+message ID.
- Deterministic normalization runs before extraction.
- Phase2 extraction job uses OpenAI Responses API with strict validation.
- Deterministic routing and event upsert create/update canonical event clusters.
- Digest job performs deterministic selection/state management plus optional LLM synthesis to publish structured briefings.

Implementation ownership:
- bounded contexts in `app/contexts/*`
- cross-context orchestration in `app/workflows/*`
- canonical digest/report semantics in `app/digest/*`

## Target-State Pipeline

1. Raw ingest
2. Structural normalization
3. AI extraction of literal reported claim
4. Deterministic post-processing / triage
5. Event clustering
6. Entity indexing / dataset construction
7. Deferred enrichment / external validation
8. Scheduled reporting

## Interpretation Guardrails

- Raw messages are source-of-record observations.
- Extraction outputs represent what was reported, not what is verified.
- `confidence` and `impact_score` are extraction/triage signals, not truth confirmation.

## Quick Reading Path

1. `ARCHITECTURE.md`
2. `../02-flows/DATA_FLOW.md`
3. `../03-interfaces/schemas_and_storage_model.md`
4. `../04-operations/operations_and_scheduling.md`
5. `../05-audit/spec_vs_impl_audit.md`

