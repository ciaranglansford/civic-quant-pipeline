### Story OPS-03 – Add Phase 2 processing observability signals

- **Story ID**: OPS-03
- **Title**: Emit logs and metrics for extraction run health
- **As a**: Operator
- **I want**: Structured operational visibility into Phase 2 runs and failures.
- **So that**: I can diagnose stuck runs, validation errors, and provider issues quickly.

#### Preconditions

- Scheduler and processing service are implemented.

#### Acceptance Criteria

- Logs include stable keys for each run/message:
  - `processing_run_id`, `raw_message_id`, `status`, `attempt_count`, `prompt_version`, `model_name`, `event_fingerprint` (when available).
- Run-level summary log is emitted at completion with counts and duration.
- Failure logs differentiate `provider_error`, `validation_error`, and `persistence_error` classes.
- At least one machine-readable metric surface is added (counter/timer logs or metrics hooks) for:
  - runs started/completed/failed
  - messages completed/failed
  - retry count
- Ops docs include failure-state diagnosis guidance for Phase 2.

#### Out-of-scope

- Full external observability stack deployment.
