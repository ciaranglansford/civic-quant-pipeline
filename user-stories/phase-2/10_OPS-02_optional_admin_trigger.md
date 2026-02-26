### Story OPS-02 – Add optional internal manual trigger endpoint for Phase 2

- **Story ID**: OPS-02
- **Title**: Expose admin-only endpoint to trigger one Phase 2 run
- **As a**: Operator
- **I want**: A manual trigger for emergency/backfill runs that reuses the scheduler service.
- **So that**: I can run extraction on demand without duplicating orchestration logic.

#### Preconditions

- Shared Phase 2 processing service exists.
- Internal auth approach for admin routes is available or planned.

#### Acceptance Criteria

- A FastAPI endpoint (for example `POST /admin/process/phase2-extractions`) is added and marked internal-only in docs.
- Endpoint calls the exact same service used by scheduler entrypoint.
- Endpoint response includes `processing_run_id` and run summary counters.
- Endpoint enforces configured admin auth guard (or is feature-flagged disabled by default if auth is not yet available).
- API tests cover authorized success and unauthorized rejection.

#### Out-of-scope

- Public UI exposure of this trigger.
