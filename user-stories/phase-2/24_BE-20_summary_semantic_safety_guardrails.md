### Story BE-20 - Add summary semantic safety guardrails for extraordinary claims

* **Story ID**: BE-20
* **Title**: Apply deterministic summary safety rewrite for high-risk unattributed claims
* **As a**: Backend engineer
* **I want**: A minimal deterministic safety pass on canonical summaries.
* **So that**: Downstream output preserves reported-claim framing and avoids sounding like verified fact for extraordinary claims.

#### Preconditions

* Canonicalization flow exists and runs before triage/routing/event updates.
* Raw validated extraction payload is persisted separately from canonical payload.

#### Acceptance Criteria

* High-risk claim indicators are detected deterministically from summary text.
* Attribution markers are detected deterministically.
* Safety gate rewrites only when high-risk language exists without attribution markers.
* Rewrite strategy is minimal and deterministic.
  * Uses available structured entities/source fields.
  * Avoids adding facts not present in extraction context.
* Pronoun disambiguation is applied only when replacement entity/source is available in structured fields.
* Raw/canonical separation is preserved.
  * `payload_json` remains untouched.
  * Safety rewrite applies in canonical payload path only.
* Canonicalization rule IDs include safety-related rules through existing metadata/rule plumbing.

#### Out-of-scope

* Prompt-level regeneration or free-form summary rewriting.
