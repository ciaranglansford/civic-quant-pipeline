# Glossary

- Raw message: immutable source bulletin row in `raw_messages`.
- Observation: one ingested bulletin instance.
- Reported claim: what source text says; not a confirmed fact.
- Extraction: structured claim payload produced from normalized message text.
- Canonical payload: deterministic normalized extraction payload used by downstream logic.
- Replay identity: deterministic key for reuse on the same raw message + extraction contract.
- Content reuse: reuse of canonical extraction from prior message with matching normalized text and contract.
- Event: evolving cluster of related observations in `events`.
- Claim hash: deterministic claim-comparison hash for update/no-op/conflict decisions.
- Hard identity: authoritative backend fingerprint (`event_identity_fingerprint_v2`).
- Soft match: contextual similarity matching fallback (entities/keywords/source/time window).
- Triage action: deterministic action class (`archive`, `monitor`, `update`, `promote`).
- Enrichment route: deterministic route (`store_only`, `index_only`, `deep_enrich`).
- Digest artifact: persisted canonical digest output (`digest_artifacts`).
- Covered event IDs: source event ids represented by digest bullets.
- Theme evidence: deterministic match row linking event/extraction to a theme.
- Assessment: persisted scored theme opportunity analysis row.
- Thesis card: generated card output with emitted/suppressed/draft status.
