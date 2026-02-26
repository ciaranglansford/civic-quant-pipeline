## LLM Usage and Prompt Plan

This document defines how LLMs will be used in the Civicquant Intelligence Pipeline. In Phase 1 MVP, extraction may be stubbed, but the interfaces and schemas must match this plan exactly.

### 1. ExtractionAgent

#### Purpose

- Convert `normalized_text` from a single Telegram message into structured JSON fields matching `llm_extraction_schema`.
- Provide scores and a stable `event_fingerprint` for dedup and routing.

#### Inputs

- `normalized_text: string`
- `message_time: ISO8601 datetime`
- `source_channel_name: string`

#### Outputs (Extraction JSON)

- `topic: string(enum)` – one of:
  - `macro_econ`, `central_banks`, `equities`, `credit`, `rates`, `fx`, `commodities`, `crypto`, `war_security`, `geopolitics`, `company_specific`, `other`
- `entities`:
  - `countries: string[]`
  - `orgs: string[]`
  - `people: string[]`
  - `tickers: string[]`
- `affected_countries_first_order: string[]`
- `market_stats: object[]` – each:
  - `label: string`
  - `value: number`
  - `unit: string`
  - `context: string`
- `sentiment: string(enum)` – `positive`, `negative`, `neutral`, `mixed`, `unknown`
- `confidence: number(0..1)`
- `impact_score: number(0..100)`
- `is_breaking: boolean`
- `breaking_window: string(enum)` – `15m`, `1h`, `4h`, `none`
- `event_time: string(ISO8601) | null`
- `source_claimed: string | null`
- `summary_1_sentence: string`
- `keywords: string[]`
- `event_fingerprint: string`

#### Prompt Skeleton (for future LLM implementation)

- **System message**:
  - Explain role: extract structured, market-relevant facts.
  - Enforce no trading advice or prescriptive interpretation.
  - Require strict adherence to JSON schema with no extra fields.
- **User message**:
  - Include:
    - `normalized_text`
    - `message_time`
    - `source_channel_name`
  - Include the complete JSON schema with:
    - Field descriptions.
    - Enum values and numeric ranges.
  - Ask the model to return ONLY a single JSON object.

#### Validation Checklist

- All required fields present.
- Enums are valid.
- Numeric ranges respected (`0..1`, `0..100`).
- `event_fingerprint` is non-empty and deterministic given the input.

### 2. EvidenceAgent (Phase 2+)

In Phase 1, this agent is **not used**. This section documents future behavior.

#### Purpose

- Given `extraction_json`, fetch supporting URLs and estimate reliability of the claim.

#### Inputs

- `extraction_json` as produced by `ExtractionAgent`.

#### Outputs

- `evidence_sources: []` of:
  - `publisher: string`
  - `title: string`
  - `url: string`
  - `published_time: string(ISO8601) | null`
  - `snippet: string`
- `corroboration_status: string(enum)` – `corroborated`, `partially_corroborated`, `uncorroborated`, `unknown`
- `reliability_score: number(0..100)`
- `notes: string`

#### Guardrails

- Never fabricate URLs or publishers.
- If no corroboration is found, label as `uncorroborated` and lower publish priority downstream.

### 3. RoutingAgent (Optional, Hybrid Mode)

In Phase 1, routing is purely rules-based. This section documents an optional future agent.

#### Purpose

- Suggest destinations and publish priority as hints to the rules engine.

#### Inputs

- `extraction_json`
- Optional `evidence_summary`

#### Outputs

- `suggested_destinations: string[]`
- `publish_priority_suggestion: string(enum)` – `none`, `low`, `medium`, `high`

### 4. PublisherAgent

#### Purpose

- Generate digest and long-form text from event queries, respecting tone and safety rules.

#### Inputs

- `events_query_results` – structured events with summaries, impact, topics, and evidence (where available).

#### Outputs

- `final_post_text: string`
- `metadata: object` – e.g., categories included, time window, counts.
- `content_hash: string`

#### Digest Template Shape (Phase 1)

- **Header**:
  - Time window (e.g., `Last 4 hours`).
  - High-level counts (events per topic).
- **Body grouped by topic**:
  - Topic heading (e.g., `Macro / Central Banks`).
  - For each event:
    - 1-sentence summary.
    - Key numbers and entities.
    - Corroboration label: `unknown` (Phase 1) or from evidence later.
- **Footer**:
  - Disclaimers: no investment advice; informational only.


## 5. Phase 2 ExtractionAgent Prompt Governance (Execution Contract)

For scheduled backend processing, the ExtractionAgent prompt flow must remain deterministic and auditable.

### Prompt Template Ownership

- Prompt template file is checked into the backend repository and versioned (e.g., `extraction_agent_v1`).
- Processing code loads template from disk and injects only:
  - `normalized_text`
  - `message_time`
  - `source_channel_name`
- Each persisted extraction stores the `prompt_version` used.

### Non-negotiable Output Constraints

- Return exactly one JSON object.
- No markdown, prose, or code fences.
- No additional keys beyond the extraction schema fields.
- Enum values must match allowed values exactly.
- Numeric fields must satisfy defined ranges.
- `event_fingerprint` must be deterministic and repeatable for equivalent facts.

### Runtime Validation Requirement

- Validation occurs before DB persistence using strict schema parsing.
- Invalid JSON or schema violations are recorded as failed processing attempts with explicit error reason.
- Failed attempts are retryable under scheduler policy; completed rows are not reprocessed.
