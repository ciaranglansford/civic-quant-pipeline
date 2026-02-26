### Story OPS-01 – Add 10-minute Phase 2 scheduler with concurrency guard

- **Story ID**: OPS-01
- **Title**: Run extraction processing every 10 minutes without overlapping runs
- **As a**: Operator
- **I want**: A scheduled job entrypoint for Phase 2 with single-run concurrency protection.
- **So that**: Processing runs are regular, safe, and do not duplicate work under overlap.

#### Preconditions

- Phase 2 processing orchestrator service exists.

#### Acceptance Criteria

- A new job entrypoint exists (for example `app/jobs/run_phase2_extraction.py`) that invokes the shared service.
- Operations docs provide a cron example for 10-minute cadence.
- A concurrency guard prevents overlapping runs (DB advisory lock, lock row, or equivalent).
- If lock acquisition fails due to active run, job exits cleanly with informative log and no processing.
- Scheduler job commits/rolls back DB transactions safely on success/failure.
- Tests verify overlapping invocation behavior and lock-release on completion.

#### Out-of-scope

- Distributed queue infrastructure.
