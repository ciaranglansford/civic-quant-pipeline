### Story BE-23 - Tighten pronoun rewrite safety and grammar guardrails

* **Story ID**: BE-23
* **Title**: Prevent malformed canonical summaries from over-aggressive pronoun disambiguation
* **As a**: Backend engineer
* **I want**: Deterministic guardrails that limit pronoun replacement to safe grammatical contexts.
* **So that**: Canonical summaries remain readable, accurate, and attribution-safe without semantic corruption.

#### Preconditions

* Canonical summary safety rewrite runs in deterministic post-processing.
* Raw/canonical payload separation is already enforced.

#### Acceptance Criteria

* Pronoun disambiguation applies only when deterministic grammatical safety checks pass.
  * Restrict replacement to subject-position pronouns where entity substitution is unambiguous.
  * Skip replacement for known unsafe patterns (for example modal-verb continuation phrases).
* Replacement source must remain bounded to structured extraction fields.
  * Use `source_claimed` first, then canonical entities if safe.
  * Never inject entities not present in extraction payload.
* High-risk attribution rewrite remains canonical-only and deterministic.
* Rule IDs capture both applied and skipped behavior.
  * e.g. `summary_pronoun_disambiguated`, `summary_pronoun_skip_unsafe_context`
* Regression tests cover:
  * valid safe replacement case,
  * unsafe-context skip case,
  * raw payload unchanged while canonical may differ.

#### Out-of-scope

* Full natural-language generation or prompt redesign.
