### Story INF-02 – Implement OpenAI ExtractionAgent client

- **Story ID**: INF-02
- **Title**: Call OpenAI with strict ExtractionAgent prompt and bounded retries
- **As a**: Backend engineer
- **I want**: A dedicated OpenAI client service for Phase 2 extraction.
- **So that**: Eligible raw messages can be transformed into structured extraction JSON.

#### Preconditions

- Prompt template loader and OpenAI settings are implemented.

#### Acceptance Criteria

- A service module (for example `app/services/extraction_llm_client.py`) exists that:
  - Sends rendered prompt to configured model.
  - Enforces request timeout from config.
  - Retries only retryable failures up to configured max retries.
  - Returns raw response text and model metadata needed for auditing.
- Non-retryable failures (authentication, invalid request) are surfaced as terminal errors for the message.
- Retryable failures (transient network/5xx/rate limit) are logged with bounded backoff.
- The client is isolated behind an interface so scheduler/service tests can mock it.

#### Out-of-scope

- Using this client for PublisherAgent or other future agents.
