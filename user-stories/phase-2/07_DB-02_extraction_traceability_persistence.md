### Story DB-02 – Persist extraction outputs with run traceability

- **Story ID**: DB-02
- **Title**: Extend extraction persistence for prompt/run/raw-response auditability
- **As a**: Operator
- **I want**: Stored linkage between each processed message, prompt version, and LLM raw output.
- **So that**: Failures and model behavior can be audited and replayed.

#### Preconditions

- `extractions` table exists with `raw_message_id`, `model_name`, and `extraction_json`.

#### Acceptance Criteria

- Persistence model is extended to store at least:
  - `prompt_version`
  - `processing_run_id`
  - `llm_raw_response` (text or JSON)
  - `validated_at` timestamp
- Each successful Phase 2 extraction insert includes these trace fields.
- On duplicate/re-run for same `raw_message_id`, persistence remains idempotent (no second extraction row).
- Query path exists to inspect extraction by `raw_message_id` and its `processing_run_id`.
- Tests verify trace fields are stored and preserved across duplicate run attempts.

#### Out-of-scope

- Long-term archival/retention policy for raw LLM responses.
