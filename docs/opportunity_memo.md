# Opportunity Memo v1 (Investable Thesis Contract)

## Purpose

Opportunity Memo v1 is a CLI-first, on-demand workflow that produces one **single-topic, client-facing investment memo** for a UTC half-open window `[start, end)`.

The product goal is not generic commentary. It is a concrete, evidence-backed thesis memo that answers:

- what the opportunity is
- what target/exposure it relates to
- why now
- why it is actionable financially
- how a financially literate client might express the view
- what invalidates it and what to monitor next

## Scope and Non-Goals

Included:
- deterministic topic ranking (or manual topic override)
- deterministic internal memo input pack from event-layer data
- deterministic primary-driver selection
- external web enrichment through a normalized source contract
- strict structured writer contract
- hard quality validation (not only structural validation)
- persistence + Telegram delivery with explicit run states

Excluded:
- `get_previous_memo_context`
- multi-topic memo generation
- additional providers (OpenAI-only default seam in v1)
- new HTTP endpoint
- use of `raw_messages` for memo composition

## CLI Entrypoints

```bash
python -m app.jobs.adopt_opportunity_memo_schema
python -m app.jobs.run_opportunity_memo --start <iso-utc> --end <iso-utc> [--topic <topic>]
```

Examples:

```bash
python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z
python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z --topic natural_gas
```

## Deterministic Topic Logic

Topic universe is fixed:

- `natural_gas`
- `lng`
- `oil`
- `fertilizers`
- `grains`
- `power`
- `shipping`
- `carbon`
- `coal`

Topic mapping precedence is strict:

1. `event_tags`
2. `event_relations`
3. latest extraction canonical payload
4. no match

Rules:
- no `raw_messages`
- no hidden LLM topic classification
- diagnostics are returned (`source_layer`, matched fields, reason trail)

## Topic Ranking and Novelty

Auto-selection score:

```text
topic_score =
  0.30 * normalized_event_count
+ 0.25 * normalized_weighted_impact
+ 0.20 * normalized_novelty
+ 0.15 * normalized_coherence
+ 0.10 * normalized_actionability
```

Novelty is narrow and deterministic:
- compare selected-topic event identities against immediately prior equivalent window
- identity precedence:
  - `event_identity_fingerprint_v2`
  - `claim_hash`
  - `event_id`
- optional simple recent-same-topic memo penalty

If no topic crosses threshold, run exits as `no_topic_found` and does not publish.

## Internal Input Pack (Deterministic)

Writer receives deterministic internal context including:

- `selected_event_ids`
- `event_timeline`
- `selected_primary_driver`
- `topic_event_stats` (count/impact/recency summary)
- `driver_evidence_summary`
- `supporting_fact_candidates` (deterministic candidate facts)

Boundary:
- `selection_diagnostics` is orchestration/debug metadata only
- writer evidence uses only internal event evidence + normalized external evidence

## External Evidence Contract

Provider seam:
- `OpportunityResearchProvider` protocol
- `OpenAiOpportunityResearchProvider` default implementation

Normalized source shape:
- `source_id`
- `source_type`
- `title`
- `publisher`
- `retrieved_at`
- `query`
- `summary`
- `claim_support_tags`
- `url` (if available)

Raw provider payloads do not flow into memo writing logic.

## Memo Artifact Contract

Canonical output is structured JSON (`OpportunityMemoStructuredArtifact`) with required fields:

- `title`
- `core_thesis_one_liner`
- `opportunity_target`
- `market_setup`
- `background`
- `primary_driver`
- `supporting_developments`
- `why_now`
- `why_this_is_an_opportunity`
- `trade_expression`
- `quantified_evidence_points`
- `risks`
- `invalidation_triggers`
- `watchpoints`
- `confidence_level` (`low|medium|high`)
- `conclusion`
- `traceability`

## Traceability Rules (Hard)

These thesis-bearing sections must always be traceable:

- `core_thesis_one_liner`
- `market_setup`
- `background`
- `primary_driver`
- `supporting_developments`
- `why_now`
- `why_this_is_an_opportunity`
- `trade_expression`
- `quantified_evidence_points`
- `risks`
- `invalidation_triggers`
- `watchpoints`
- `conclusion`

Notes:
- `title` is exempt
- `confidence_level` is metadata-backed (not paragraph-traced)
- each traced paragraph key maps to:
  - `internal_event_ids`
  - `external_source_ids`

## Hard Validation Gates (Quality + Structure)

Memo is rejected (`validation_failed`) if any hard rule fails, including:

- missing required sections
- insufficient supporting events / external sources
- missing primary driver
- missing required traceability
- invalid traceability source IDs
- topic drift
- generic `opportunity_target`
- weak `core_thesis_one_liner`
- generic `why_now`
- vague `trade_expression`
- generic `why_this_is_an_opportunity`
- insufficient quantitative evidence in `quantified_evidence_points`
- filler or low-substance list content

This intentionally rejects broad sector commentary even if prose quality is high.

## Run States

Persisted states:

- `running`
- `no_topic_found`
- `validation_failed`
- `completed`
- `delivery_failed`

## Persistence Model

Tables:
- `opportunity_memo_runs`
- `opportunity_memo_artifacts`
- `opportunity_memo_input_events`
- `opportunity_memo_external_sources`
- `opportunity_memo_deliveries`

Persisted values include:
- window/topic/score/driver selection
- memo JSON
- traceability JSON
- linked input events and external sources
- delivery outcomes

Hashes:
- `input_hash`: deterministic hash of window/topic/event IDs/driver/settings
- `canonical_hash`: deterministic hash of validated structured memo artifact

## Telegram Rendering

Renderer is memo-specific and evidence-forward. It surfaces:

- core thesis
- opportunity target
- market setup
- primary driver
- quantified evidence points
- why now
- why this is an opportunity
- trade expression
- risks
- invalidation triggers
- watchpoints
- confidence level
- conclusion

## MCP Read-Only Tools

Added memo-oriented read-model tools:

1. `rank_topic_opportunities`
2. `build_opportunity_memo_input`
3. `get_topic_timeline`
4. `get_topic_driver_pack`

`get_previous_memo_context` is explicitly deferred in v1.

## API Surface

Opportunity Memo v1 is CLI-first.
- no new HTTP endpoint in v1
