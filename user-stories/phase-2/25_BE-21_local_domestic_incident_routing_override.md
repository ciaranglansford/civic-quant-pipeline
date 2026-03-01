### Story BE-21 - Add narrow routing overrides for local domestic incident patterns

* **Story ID**: BE-21
* **Title**: Deterministically downgrade local domestic incident urgency without taxonomy redesign
* **As a**: Backend engineer
* **I want**: A narrow local-incident override in deterministic triage/routing.
* **So that**: Domestic public-safety incident bullets do not receive conflict-level urgency by default.

#### Preconditions

* Deterministic triage and routing services are active in Stage 4.
* Existing topic taxonomy is persisted and consumed downstream.

#### Acceptance Criteria

* Local domestic incident pattern detection is deterministic.
  * Local authority/police markers.
  * Public-safety injury/incident phrasing.
  * Local geography cues.
  * Absence of strong cross-border/military conflict markers.
* Matching rows are downgraded in urgency.
  * Capped to monitor-or-lower behavior.
  * Forced evidence-required routing override.
* Topic labels remain unchanged in Stage 1 unless existing safe remap behavior already exists.
* Documentation clarifies score interpretation for routing.
  * Confidence/impact are bounded model signals.
  * Deterministic score-band logic governs routing actioning.

#### Out-of-scope

* Broad taxonomy redesign or new topic families.
