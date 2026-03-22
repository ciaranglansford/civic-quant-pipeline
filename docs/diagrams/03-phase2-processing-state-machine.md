# 03 Phase2 Processing State Machine
Why this diagram matters: It captures how `message_processing_states` supports retries, lease recovery, and clear terminal outcomes while phase2 job execution is serialized by a named processing lock.

Primary source files used:
- `app/workflows/phase2_pipeline.py`
- `app/models.py`
- `docs/system-flow.md`
- `docs/data-model.md`

```mermaid
stateDiagram-v2
    state "phase2_extraction lock (processing_locks)" as Lock {
        [*] --> Idle
        Idle --> Held : _acquire_lock(run_id) succeeds
        Held --> Held : concurrent run returns lock_busy summary
        Held --> Idle : _release_lock(owner_run_id)
    }

    [*] --> Pending : ingest insert\nstatus=pending\nattempt_count=0
    Pending --> InProgress : selected by phase2 batch\nstatus=in_progress\nattempt_count += 1\nlast_attempted_at=now\nlease_expires_at=now+lease\nlast_error=null
    Failed --> InProgress : reselected on later batch\nsame transition field updates
    InProgress --> InProgress : lease_expires_at <= now\neligible for reclaim
    InProgress --> Completed : extraction+triage+persistence succeed\ncompleted_at=now\nlease_expires_at=null
    InProgress --> Failed : validation/provider/persistence error\nlast_error set
    Completed --> [*]
```

## Reading Notes
- The lock is run-scoped (`processing_locks`), while message status is row-scoped (`message_processing_states`).
- `in_progress` is not terminal; expired leases make those rows eligible again.
- `attempt_count` and `last_attempted_at` update before extraction work starts.
- `completed_at` only sets on success, and lease is cleared.
- Failures preserve retryability and store error class in `last_error`.
