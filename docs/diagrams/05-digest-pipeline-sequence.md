# 05 Digest Pipeline Sequence
Why this diagram matters: It documents digest construction and publication invariants, including deterministic selection, LLM synthesis fallback behavior, and artifact-first publication safety.

Primary source files used:
- `app/digest/orchestrator.py`
- `app/digest/query.py`
- `app/digest/builder.py`
- `app/digest/synthesizer.py`
- `app/digest/artifact_store.py`
- `app/digest/dedupe.py`
- `app/digest/renderer_text.py`
- `app/models.py`

```mermaid
sequenceDiagram
    participant Trigger as "Job/Admin trigger"
    participant Orch as "digest.orchestrator"
    participant Query as "digest.query"
    participant Builder as "digest.builder"
    participant Synth as "digest.synthesizer"
    participant OpenAI as "OpenAI digest synthesis"
    participant Render as "digest.renderer_text"
    participant Store as "digest.artifact_store"
    participant DB as "DB"
    participant Adapter as "Destination adapter"

    Trigger->>Orch: run_digest(window_hours)
    Orch->>Orch: freeze digest window
    Orch->>Orch: resolve enabled adapters

    loop each destination
        Orch->>Query: get_events_for_window(window, min_impact>25, destination)
        Query->>DB: select by last_updated_at + destination unpublished filter
        DB-->>Query: candidate events
        Query-->>Orch: deterministic event set

        alt no events
            Orch-->>Trigger: destination status=skipped_no_events
        else events selected
            Orch->>Builder: build_source_digest_events() [DET]
            Builder->>Builder: pre_dedupe_source_events() [DET]
            Orch->>Synth: synthesize_digest(window, sources, groups)

            alt LLM enabled and client available
                Synth->>OpenAI: synthesize(prompt) [LLM]
                OpenAI-->>Synth: JSON draft digest
                Synth->>Synth: strict schema and coverage validation [DET]
                alt synthesis valid
                    Synth-->>Orch: validated canonical digest
                else provider/template/validation failure
                    Synth-->>Orch: deterministic fallback digest
                end
            else LLM disabled/unavailable
                Synth-->>Orch: deterministic fallback digest
            end

            Orch->>Render: render_canonical_text() [DET]
            Orch->>Store: input_hash_for_digest_inputs() [DET]
            Orch->>Store: get_or_create_artifact() [DET]
            Store->>DB: select/insert digest_artifacts
            Note over Orch,DB: Invariant: artifact must exist and be committed before any publish attempt.
            Orch->>DB: commit artifact transaction

            Orch->>Adapter: render_payload(canonical_digest, canonical_text) [DET]
            Orch->>DB: destination_already_published(artifact_id, destination)
            alt already published
                Orch-->>Trigger: destination status=skipped_published
            else not yet published
                Orch->>DB: upsert published_posts attempt row
                Orch->>Adapter: publish(payload)
                alt publish success
                    Adapter-->>Orch: status=published
                    Orch->>DB: mark covered source events published for destination
                    Orch->>DB: update published_posts + commit
                else publish failure or exception
                    Adapter-->>Orch: status=failed or exception
                    Orch->>DB: update published_posts status=failed + last_error + commit
                end
            end
        end
    end
```

## Reading Notes
- Event selection is deterministic and destination-aware (`is_published_*` filter).
- Deterministic pre-dedupe runs before any synthesis request.
- LLM synthesis is optional and guarded by strict post-validation; fallback is deterministic.
- Artifact persistence/commit is a hard invariant before publish attempts.
- Publish state is tracked per destination in `published_posts`; successful sends mark covered events as published.
