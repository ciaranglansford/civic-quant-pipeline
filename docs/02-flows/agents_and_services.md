## Agents and Services

### Purpose

Describe the logical agents and services in the Civicquant pipeline, including inputs, outputs, side effects, and Phase 1 status.

### ExtractionAgent

- **Responsibility**: Convert normalized text and message metadata into structured extraction JSON.
- **Phase 1 status**: Implemented as stub (no external LLM calls).

#### Inputs

- `normalized_text: string`
- `message_time: datetime`
- `source_channel_name: string`

#### Outputs

- `extraction_json` object with fields:
  - `topic`
  - `entities` (countries, orgs, people, tickers)
  - `affected_countries_first_order`
  - `market_stats`
  - `sentiment`
  - `confidence`
  - `impact_score`
  - `is_breaking`
  - `breaking_window`
  - `event_time`
  - `source_claimed`
  - `summary_1_sentence`
  - `keywords`
  - `event_fingerprint`

#### Side Effects

- None directly; caller persists output to `extractions` table.

#### Expected Code Location

- Service module in backend (e.g., `app/services/extraction_agent.py`).

### EvidenceAgent

- **Responsibility**: Fetch supporting sources and estimate reliability for high-impact or breaking events.
- **Phase 1 status**: Not implemented (documented for Phase 2+).

#### Inputs

- `extraction_json` from `ExtractionAgent`.

#### Outputs

- `evidence_sources[]`
- `corroboration_status`
- `reliability_score`
- `notes`

#### Side Effects

- External HTTP calls to news/search APIs.
- Writes to `evidence_sources` table (future).

### RoutingAgent (Optional)

- **Responsibility**: Optionally suggest routing destinations and priorities to complement rules engine.
- **Phase 1 status**: Not used; routing is purely rules-based.

#### Inputs

- `extraction_json`
- Optional evidence summary.

#### Outputs

- `suggested_destinations[]`
- `publish_priority_suggestion`

### Routing Rules Engine

- **Responsibility**: Determine `routing_decision` from extraction (and evidence in later phases).
- **Phase 1 status**: Implemented as deterministic rules.

#### Inputs

- `extraction_json`
- Routing configuration (thresholds, mappings).

#### Outputs

- `routing_decision` with:
  - `store_to[]`
  - `publish_priority`
  - `requires_evidence`
  - `event_action`
  - `flags[]`

#### Side Effects

- Inserts into `routing_decisions` table.

### EventManagerAgent

- **Responsibility**: Manage canonical events and deduplication.
- **Phase 1 status**: Implemented with fingerprint-based matching and time windows.

#### Inputs

- `extraction_json`
- `raw_message_id`

#### Outputs

- `event_action` (`create` or `update`)
- `event_id`

#### Side Effects

- Inserts/updates in `events` table.
- Inserts in `event_messages` table.
- Logging of dedup and update decisions.

### PublisherAgent

- **Responsibility**: Build digests and long-form posts from event data.
- **Phase 1 status**: Implemented for 4-hour VIP digests only.

#### Inputs

- `events_query_results` for time window.

#### Outputs

- `final_post_text`
- `metadata`
- `content_hash`

#### Side Effects

- Sends messages via Telegram Bot API.
- Inserts into `published_posts` table.


## Phase 2 ExtractionAgent Contract (Authoritative Behavior)

For scheduled Phase 2 processing, ExtractionAgent execution must follow the repository prompt contract in `plans/llm_usage_and_prompts.md`.

### Required Inputs

- `normalized_text`
- `message_time`
- `source_channel_name`

### Required Output Fields (exact; no extra keys)

- `topic`
- `entities.countries`
- `entities.orgs`
- `entities.people`
- `entities.tickers`
- `affected_countries_first_order`
- `market_stats[]`
- `sentiment`
- `confidence`
- `impact_score`
- `is_breaking`
- `breaking_window`
- `event_time`
- `source_claimed`
- `summary_1_sentence`
- `keywords`
- `event_fingerprint`

### Non-negotiable Runtime Rules

- JSON-only model output.
- No additional properties.
- Enum and numeric range validation enforced before persistence.
- `event_fingerprint` must be deterministic for equivalent input facts.
- Prompt template is versioned and stored in-repo; each run persists `prompt_version`.
