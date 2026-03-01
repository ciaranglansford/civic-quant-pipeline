### Story BE-19 - Refine related-bulletin convergence without collapsing raw observations

* **Story ID**: BE-19
* **Title**: Use strict soft-related detection for triage calibration while preserving exact event linking
* **As a**: Backend engineer
* **I want**: Follow-on bulletin relatedness to influence urgency calibration without unsafe event over-merging.
* **So that**: Repetitive updates converge behaviorally while event association remains safe and deterministic.

#### Preconditions

* Exact fingerprint + window event association exists in `event_manager`.
* Canonical entities/countries are available for deterministic overlap checks.

#### Acceptance Criteria

* Exact match remains first and only event association path in Stage 1.
  * `upsert_event` does not perform soft-related reassignment fallback.
* Secondary soft-related checks are deterministic and bounded in time.
  * Same topic.
  * Recent short window.
  * Exact fingerprint match or minimum canonical entity/country overlap threshold.
* Soft-related checks are used only for triage/routing calibration.
  * Novelty classification support.
  * Repetition downgrade handling.
  * Publish-priority cap behavior.
* Observation-level records remain preserved.
  * No deletion/collapse of `raw_messages`.
  * Message-to-event linkage remains explicit and auditable.

#### Out-of-scope

* Broad fuzzy matching or probabilistic event clustering.
