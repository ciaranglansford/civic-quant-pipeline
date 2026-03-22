# 01 Bounded Context Map
Why this diagram matters: It shows the modular-monolith ownership boundaries so a new engineer can quickly see where HTTP entrypoints, orchestration, domain logic, and persistence responsibilities live.

Primary source files used:
- `app/main.py`
- `app/routers/ingest.py`
- `app/routers/feed.py`
- `app/routers/admin.py`
- `app/routers/admin_theme.py`
- `app/workflows/phase2_pipeline.py`
- `app/workflows/deep_enrichment_pipeline.py`
- `app/workflows/theme_batch_pipeline.py`
- `app/contexts/*`
- `app/digest/*`
- `app/db.py`
- `app/models.py`

```mermaid
flowchart LR
  subgraph APP["FastAPI App"]
    MAIN["app/main.py create_app()"]
    R_INGEST["router: ingest"]
    R_ADMIN["router: admin"]
    R_THEME["router: admin_theme"]
    R_FEED["router: feed"]
    MAIN --> R_INGEST
    MAIN --> R_ADMIN
    MAIN --> R_THEME
    MAIN --> R_FEED
  end

  subgraph WF["Orchestration Workflows (app/workflows/*)"]
    W_PHASE2["phase2_pipeline"]
    W_DEEP["deep_enrichment_pipeline"]
    W_THEME["theme_batch_pipeline"]
  end

  subgraph CTX["Bounded Contexts (app/contexts/*)"]
    C_ING["ingest"]
    C_EXT["extraction"]
    C_TRI["triage"]
    C_EVT["events"]
    C_ENT["entities"]
    C_ENR["enrichment"]
    C_THE["themes"]
    C_OPP["opportunities"]
    C_FEED["feed"]
  end

  subgraph DIG["Digest Module (app/digest/*)"]
    D_ORCH["orchestrator"]
    D_QUERY["query"]
    D_BUILD["builder"]
    D_SYN["synthesizer"]
    D_STORE["artifact_store + dedupe"]
    D_ADAPTER["adapters"]
    D_ORCH --> D_QUERY
    D_ORCH --> D_BUILD
    D_ORCH --> D_SYN
    D_ORCH --> D_STORE
    D_ORCH --> D_ADAPTER
  end

  subgraph DATA["Persistence Layer"]
    DB["app/db.py session"]
    MODELS["app/models.py tables"]
    DB --> MODELS
  end

  OPENAI["OpenAI Responses API"]
  TELEGRAM["Telegram source + digest destination"]

  R_INGEST --> C_ING --> DB
  R_FEED --> C_FEED --> DB

  R_ADMIN --> W_PHASE2
  R_ADMIN --> W_DEEP
  R_ADMIN --> D_ORCH
  R_THEME --> W_THEME

  W_PHASE2 --> C_EXT
  W_PHASE2 --> C_TRI
  W_PHASE2 --> C_EVT
  W_PHASE2 --> C_THE
  W_PHASE2 --> C_ENR
  W_PHASE2 --> C_ENT

  W_DEEP --> C_ENR
  W_THEME --> C_THE
  W_THEME --> C_OPP

  C_EXT --> OPENAI
  D_SYN --> OPENAI
  D_ADAPTER --> TELEGRAM

  C_EXT --> DB
  C_TRI --> DB
  C_EVT --> DB
  C_THE --> DB
  C_ENT --> DB
  C_ENR --> DB
  C_OPP --> DB
  D_ORCH --> DB
```

## Reading Notes
- Routers are thin entrypoints; workflows and digest orchestrator own sequencing.
- `phase2_pipeline` coordinates multiple bounded contexts but does not duplicate their domain logic.
- `app/digest/*` is a separate orchestration lane with its own deterministic and LLM synthesis boundary.
- All durable state changes converge on SQLAlchemy models in `app/models.py`.
- OpenAI calls are isolated to extraction and digest synthesis modules.
