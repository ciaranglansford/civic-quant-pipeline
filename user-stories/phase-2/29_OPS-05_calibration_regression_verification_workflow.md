### Story OPS-05 - Add calibration regression verification workflow for Stage 1+ quality controls

* **Story ID**: OPS-05
* **Title**: Extend local verification runbook with calibration-focused regression checks
* **As a**: Backend engineer
* **I want**: A repeatable workflow that validates triage calibration and summary safety behavior on fresh and real-world batches.
* **So that**: Pipeline quality regressions are caught before production promotion.

#### Preconditions

* Stage 1 deterministic calibration logic is deployed in code.
* Runbook and jobs documentation already cover base execution flow.

#### Acceptance Criteria

* Operations runbook includes calibration regression checklist after phase2 job execution.
  * Verify promote-throttle behavior in burst windows.
  * Verify soft-related downgrade and burst-cap rule coverage.
  * Verify canonical summary rewrite safety and grammar checks.
  * Verify raw/canonical separation remains intact.
* Verification commands include:
  * targeted SQL samples for recent-window triage distribution,
  * row-level inspection queries for rewrite quality,
  * clear expected outcomes and interpretation.
* Workflow documents escalation path when thresholds fail.
  * record failing metrics,
  * isolate likely deterministic rule source,
  * rerun preserve-raw reprocess path for validation.

#### Out-of-scope

* Automated incident response orchestration.
