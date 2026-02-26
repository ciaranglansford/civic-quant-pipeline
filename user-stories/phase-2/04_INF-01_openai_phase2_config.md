### Story INF-01 – Add Phase 2 OpenAI configuration settings

- **Story ID**: INF-01
- **Title**: Externalize OpenAI settings for ExtractionAgent runs
- **As a**: Platform engineer
- **I want**: Configured OpenAI model, timeout, and retry settings from environment variables.
- **So that**: Phase 2 can run in different environments without code changes or hardcoded secrets.

#### Preconditions

- `app/config.py` is the canonical settings module.

#### Acceptance Criteria

- `Settings` includes Phase 2 extraction config fields:
  - `openai_api_key`
  - `openai_model`
  - `openai_timeout_seconds`
  - `openai_max_retries`
  - `phase2_extraction_enabled`
  - `phase2_batch_size`
- Secrets remain environment-driven and are not committed in code/docs examples.
- Missing required OpenAI settings raise a clear startup/runtime error only for Phase 2 processor entrypoints.
- Existing Phase 1 ingest API startup remains functional when Phase 2 is disabled.
- Docs under `docs/04-operations` describe required env vars and defaults.

#### Out-of-scope

- Secret manager integration beyond environment variables.
