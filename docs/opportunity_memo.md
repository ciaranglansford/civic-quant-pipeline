# Opportunity Memo v1

## Purpose

Opportunity Memo v1 is a CLI-first, on-demand workflow that generates one client-facing opportunity memo for one topic within a custom UTC half-open window `[start, end)`.

Target reader:
- financially literate paying client
- needs actionable market framing, not generic commentary

## v1 Scope

Included:
- deterministic single-topic selection (or manual topic override)
- deterministic internal memo input pack from event-layer data
- deterministic primary-driver selection
- external web research enrichment using normalized source records
- structured memo generation with required sections
- hard validation gates (including paragraph-level traceability)
- DB persistence for runs/artifacts/evidence/delivery outcomes
- Telegram delivery attempt with memo-specific rendering
- read-only MCP report tools for memo-oriented read models

Excluded (non-goals):
- `get_previous_memo_context`
- fuzzy/historical novelty frameworks
- multi-topic memo generation
- new HTTP endpoint
- multi-provider retrieval abstraction
- use of `raw_messages` as memo evidence

## How It Relates To Existing Systems

- Digest and theme-batch systems remain unchanged and continue to serve scheduled reporting.
- Opportunity Memo v1 is additive and on-demand.
- It follows the same design principle: LLM for interpretation/writing, code for deterministic state and selection.

## CLI Contract (Primary Entrypoint)

```bash
python -m app.jobs.run_opportunity_memo --start <iso-utc> --end <iso-utc> [--topic <topic>]
```

Examples:

```bash
python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z
python -m app.jobs.run_opportunity_memo --start 2026-03-15T00:00:00Z --end 2026-03-22T00:00:00Z --topic natural_gas
```

Schema adoption utility:

```bash
python -m app.jobs.adopt_opportunity_memo_schema
```

## Topic Universe

The v1 topic set is fixed in code (`OPPORTUNITY_TOPICS`):

- `natural_gas`
- `lng`
- `oil`
- `fertilizers`
- `grains`
- `power`
- `shipping`
- `carbon`
- `coal`

## Deterministic Topic Mapping

Topic mapping precedence is strict (`app/contexts/opportunity_memo/topic_mapping.py`):

1. `event_tags`
2. `event_relations`
3. latest extraction canonical payload
4. no match

Rules:
- no `raw_messages`
- no hidden LLM classification
- every mapped event includes diagnostics (`source_layer`, matched fields, reason trail, final topic)

## Deterministic Topic Ranking

Auto-selection uses:

```text
topic_score =
  0.30 * normalized_event_count
+ 0.25 * normalized_weighted_impact
+ 0.20 * normalized_novelty
+ 0.15 * normalized_coherence
+ 0.10 * normalized_actionability
```

v1 novelty is narrow:
- compares current-topic event fingerprint identities against immediately prior equivalent window
- identity precedence: `event_identity_fingerprint_v2` -> `claim_hash` -> `event_id`
- optional simple recent-same-topic memo penalty

If top topic score is below threshold, run exits with `no_topic_found` and does not publish.

## Internal Memo Input Pack

The workflow builds a deterministic internal memo input pack before writing.

Key fields:
- `topic`
- `window`
- `selected_event_ids`
- `event_timeline`
- `candidate_driver_groups`
- `selected_primary_driver`
- `supporting_entities`
- `selection_diagnostics`

Important boundary:
- `selection_diagnostics` is orchestration/debug metadata only
- writer evidence context uses only event evidence + normalized external evidence

## Primary Driver Selection

Exactly one primary driver is selected deterministically using scored driver groups.

Driver score:

```text
driver_score =
  0.40 * supporting_event_weight
+ 0.25 * temporal_density
+ 0.20 * entity_consistency
+ 0.15 * external_confirmability_proxy
```

## External Research And Normalization

The provider seam is intentionally narrow:
- `OpportunityResearchProvider` protocol
- v1 default implementation: `OpenAiOpportunityResearchProvider`

Writer input uses normalized external evidence only (not raw provider payloads).

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

## Writer Contract

Memo output is structured JSON (`OpportunityMemoStructuredArtifact`), with required sections:

- `title`
- `thesis`
- `opportunity_target`
- `background`
- `primary_driver`
- `supporting_developments`
- `why_now`
- `action_path`
- `risks`
- `watchpoints`
- `conclusion`
- `traceability`

No markdown is used as canonical internal representation.

## Traceability Requirements

Paragraph-level traceability is mandatory for thesis-bearing sections:

- `thesis`
- `background`
- `primary_driver`
- `supporting_developments`
- `why_now`
- `action_path`
- `risks`
- `watchpoints`
- `conclusion`

Rules:
- paragraph keys are explicit (`section` or `section[index]`)
- each thesis-bearing paragraph must map to:
  - `internal_event_ids`
  - `external_source_ids`

Exceptions:
- `title` is exempt
- `opportunity_target` may be lighter if short, but must remain supportable in artifact context

## Validation Gates

Hard failures suppress memo completion:
- no topic above threshold (`no_topic_found`)
- supporting event count below minimum
- no primary driver selected
- external sources below minimum
- missing required memo sections
- missing/invalid traceability for required sections
- topic drift across unrelated topics
- vague `action_path`

Soft warnings:
- weak source diversity
- borderline score/novelty
- partial contradiction handling

## Run States

`opportunity_memo_runs.status` uses explicit states only:

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

Persisted concepts include:
- run window and selection metadata
- selected topic + score
- selected event IDs and event-level mapping diagnostics
- selected primary driver
- normalized external sources used
- structured memo + traceability map
- delivery attempts/outcomes

## Deterministic Hashes

Two explicit hashes are persisted:

- `input_hash`: canonical hash of window, selected topic, selected event IDs, selected primary driver, generation settings
- `canonical_hash`: canonical hash of validated structured memo artifact

## Telegram Delivery

- Reuses existing Telegram transport/config seam
- Uses memo-specific renderer (separate from digest formatting semantics)
- Artifact is persisted before Telegram attempt
- If Telegram fails after persistence, artifact remains and run is marked `delivery_failed`

## MCP Read-Model Tools (Read-Only)

Added DB MCP tools:

1. `rank_topic_opportunities`
2. `build_opportunity_memo_input`
3. `get_topic_timeline`
4. `get_topic_driver_pack`

All remain read-only and return report-oriented shapes for memo orchestration/debugging.

## API Surface Note

Opportunity Memo v1 is CLI-first.
- No new HTTP endpoint is added in v1.
