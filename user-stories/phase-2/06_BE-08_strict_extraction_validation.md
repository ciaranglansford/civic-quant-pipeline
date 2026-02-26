### Story BE-08 – Enforce strict JSON validation for LLM extraction output

- **Story ID**: BE-08
- **Title**: Validate OpenAI response against exact ExtractionAgent contract
- **As a**: Backend engineer
- **I want**: Strict parsing and validation of the LLM JSON response.
- **So that**: Only schema-compliant extraction data is persisted.

#### Preconditions

- LLM client returns raw text output.
- `ExtractionJson` Pydantic model exists.

#### Acceptance Criteria

- Validation flow rejects any response that:
  - Is not valid JSON.
  - Is missing required fields.
  - Includes extra fields not in the contract.
  - Violates enum or numeric bounds (`confidence` 0..1, `impact_score` 0..100).
- Validation uses a strict model mode (`extra=forbid`) for Phase 2 parsing path.
- Failed validations persist structured error reason in processing state and do not create extraction/event rows.
- Successful validations produce a typed object used for persistence mapping.
- Tests include malformed JSON, extra fields, enum violations, range violations, and valid payload pass case.

#### Out-of-scope

- Semantic truth checking of extracted facts.
