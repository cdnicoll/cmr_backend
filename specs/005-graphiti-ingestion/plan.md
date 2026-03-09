# Implementation Plan: Knowledge Graph Ingestion from Scraped Content

**Branch**: `005-graphiti-ingestion` | **Date**: 2025-03-09 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/005-graphiti-ingestion/spec.md`

## Summary

Implement a single ingestion path from scraped content to the knowledge graph: a worker accepts a resource ID, validates scraped content (e.g. minimum word count), transitions the resource to `ingesting`, sends the content to Graphiti as a text episode, then sets `pipeline_stage` to `complete` or `failed` with a stored `failure_reason`. Pipeline is **scraped → ingesting → complete** (no extracting/extracted). As part of this phase, remove all Phase 3 extraction code (PydanticAI insight agent, `InsightsService.extract_insights`, `extract_insights` Modal function, extraction-only DAO methods, insight-related config/models) and update the runbook to the ingest-only flow. Graphiti is the single extractor; Neo4j and LLM credentials are supplied via Modal secrets.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, Supabase (asyncpg/transaction pooler), Modal, graphiti-core, Neo4j (via Graphiti), OpenAI or compatible LLM/embedder for Graphiti  
**Storage**: PostgreSQL (Supabase) for resources and pipeline state; Neo4j for the knowledge graph (via Graphiti)  
**Testing**: pytest; runbook-driven manual verification for Modal workers  
**Target Platform**: Modal (workers), Supabase (DB); local dev via `scripts/dev.py`  
**Project Type**: Web service (API) + background workers  
**Performance Goals**: Ingestion completes within worker timeout (e.g. minutes per resource under normal conditions)  
**Constraints**: Worker must use env/secrets for Neo4j and LLM; no hardcoded credentials  
**Scale/Scope**: Per-resource ingestion; Phase 8 adds recovery for stuck `ingesting`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Quick Start**: No new setup steps beyond adding optional Neo4j/OpenAI vars for ingestion; existing `uv sync` and `.env` from `.env.example` remain the path. New env vars documented in runbook and `.env.example`.
- **REST API**: No new REST endpoints; health and docs unchanged.
- **Cloud-Ready**: Worker is stateless; Neo4j/Graphiti config via Modal secrets; deployment via existing `uv run deploy_dev` / `deploy_prod`.
- **Observability**: Use existing `get_logger(__name__)` and structured logging in the new ingestion service; no new request-ID requirements (worker is triggered by Modal, not HTTP).
- **Developer Guidance**: Follow `_local/starter-kit/patterns.md` (Service → DAO) and `_local/starter-kit/modal-jobs.md`; runbook updated for ingest flow.

**Result**: Pass — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-graphiti-ingestion/
├── plan.md              # This file
├── spec.md              # Feature specification
├── checklists/
│   └── requirements.md
├── research.md          # Phase 0 (optional): Graphiti/Neo4j setup notes
├── data-model.md        # Phase 1 (optional): ingestion state / episode shape
├── quickstart.md        # Phase 1 (optional): local/dev ingestion verification
└── tasks.md             # Phase 2 output (/speckit.tasks — not created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── api/                 # FastAPI routes (no new routes for Phase 4)
├── deployment/
│   ├── modal_workers.py # Add ingest_resource(); remove extract_insights()
│   └── deploy.py       # Add Neo4j + LLM vars to Modal secrets
├── models/
│   ├── config.py       # Add INGEST_MIN_WORD_COUNT, INGEST_STUCK_TIMEOUT_MINUTES; remove insight_*
│   └── resources/
│       └── resource.py # Remove EXTRACTING, EXTRACTED from PipelineStage (or leave and stop using)
├── services/
│   ├── ingestion/      # NEW: ingestion service + (optional) Graphiti client wrapper
│   │   └── service.py   # ingest_resource(resource_id): validate → transition → Graphiti → update
│   ├── supabase/
│   │   └── resources_dao.py  # Add atomic_transition_to_ingesting, update_after_ingestion; remove extraction-only
│   ├── insights/       # REMOVE or gut: agent, service (extract_insights), models (insight types)
│   └── scraping/
│       └── service.py  # Unchanged
tests/
docs/
├── runbook.md           # Replace "Insight extraction (Phase 3)" with "Ingest to Graphiti"
```

**Structure Decision**: Single backend; new `services/ingestion` domain; Modal worker in existing `deployment/modal_workers.py`; DAO extended in `resources_dao.py`; Phase 3 code removed from `services/insights` and related config/models.

## Phase 0: Research (Optional)

- **Graphiti API**: Use `add_episode(name=..., episode_body=..., source=EpisodeType.text, source_description=..., reference_time=...)`. For scraped content: `name` = e.g. `resource_{resource_id}` or resource UUID (for provenance in the graph); `episode_body` = `scraped_content["markdown"]`; `source=EpisodeType.text`; `source_description` = resource URL or title; `reference_time` = resource `updated_at` or `created_at`. See [Adding Episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes).
- **Runtime**: Install `graphiti-core` (and optional LLM extras if not OpenAI). Graphiti needs `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` and LLM/embedder env (e.g. `OPENAI_API_KEY`). Add these to Modal secrets for the ingestion worker.
- **Episode size**: Rely on Graphiti’s handling; optionally document or configure a max length if needed for context limits.

## Phase 1: Design

### 1.1 Ingestion worker flow

1. **Input**: `resource_id` (e.g. `modal run ...::ingest_resource --resource-id <uuid>`).
2. **Load**: Fetch resource by ID; require `pipeline_stage == scraped` and non-null `scraped_content`.
3. **Validate**: Require `scraped_content.markdown` (or equivalent) and word count ≥ `INGEST_MIN_WORD_COUNT` (default 100). If not met → set `pipeline_stage = failed`, `failure_reason = "Insufficient content for ingestion"` (or similar), return.
4. **Claim**: Atomic transition `scraped` → `ingesting` (new DAO method). If 0 rows updated → already claimed or not scraped → return (no failure reason change).
5. **Ingest**: Build episode (text + optional source_description, reference_time); call Graphiti `add_episode(...)`. On success → set `pipeline_stage = complete`, clear `failure_reason`. On exception → set `pipeline_stage = failed`, `failure_reason = f"{type(e).__name__}: {str(e)}"`.
6. **Idempotency**: If resource is already `ingesting` or `complete`, worker can log and return without overwriting.

### 1.2 DAO changes

- **Add**: `atomic_transition_to_ingesting(resource_id: str) -> int`: `UPDATE resources SET pipeline_stage = 'ingesting' WHERE id = $1 AND pipeline_stage = 'scraped'`; return row count.
- **Add**: `update_resource_after_ingestion(resource_id, pipeline_stage, failure_reason=None)`: set `pipeline_stage` and optionally `failure_reason` (no `insight`).
- **Remove or stop using**: `atomic_transition_to_extracting`, `update_resource_after_extraction`. Remove from exports and call sites as part of Phase 3 removal.

### 1.3 Config

- **Add**: `ingest_min_word_count` (env `INGEST_MIN_WORD_COUNT`, default 100).  
- **Add**: `ingest_stuck_timeout_minutes` (env `INGEST_STUCK_TIMEOUT_MINUTES`, default 30) for Phase 8 recovery; document in runbook.  
- **Remove**: `insight_min_word_count`, `insight_stuck_timeout_minutes`, `model_insight_extraction` (and any OPENROUTER usage only for insights).  
- **Neo4j/LLM**: Add to Settings (or document): `neo4j_uri`, `neo4j_username`, `neo4j_password`, `neo4j_database`; LLM/embedder (e.g. `openai_api_key`) for Graphiti. These must be in Modal secrets for the worker.

### 1.4 Modal

- **New function**: `ingest_resource(resource_id: str)` in `modal_workers.py`. Use same or similar image as `process_llm_job` (or a dedicated image with `graphiti-core`). Attach secrets that include Neo4j + LLM vars. Timeout e.g. 600s.  
- **Remove**: `extract_insights(resource_id)` Modal function.  
- **Secrets**: Extend `push_modal_secrets()` to add Neo4j and LLM vars to `app-config-{env}` (or a dedicated secret) so the ingestion worker can connect to Neo4j and Graphiti.

### 1.5 Phase 3 removal

- **Delete or gut**: `src/services/insights/agent.py`, `InsightsService.extract_insights` in `src/services/insights/service.py`, `src/models/insights/` (or keep models but remove from ingestion path).  
- **Remove**: `extract_insights` from `modal_workers.py`.  
- **DAO**: Remove `atomic_transition_to_extracting`, `update_resource_after_extraction` (or keep for a short deprecation period and do not call).  
- **PipelineStage**: Either remove `EXTRACTING` and `EXTRACTED` from the enum or leave and ensure no code transitions to them.  
- **Runbook**: Replace section "Insight extraction (Phase 3)" with "Ingest to Graphiti": command `modal run src.deployment.modal_workers::ingest_resource --resource-id <uuid>`, verify `scraped` → `ingesting` → `complete`, and document failures (validation, Neo4j/Graphiti errors).  
- **Optional**: Deprecate or ignore `insight` column on `resources`; do not read or write it in the new flow.

### 1.6 Stuck ingesting

- Phase 4 only adds config `INGEST_STUCK_TIMEOUT_MINUTES` and documents that Phase 8 recovery will reset resources stuck in `ingesting` longer than this. No recovery worker in Phase 4.

## Phase 2: Tasks

Use `/speckit.tasks` to generate `tasks.md` from this plan and the spec. Suggested task areas:

1. **Config and secrets**: Add ingest and Neo4j/LLM settings; update deploy script and `.env.example`; document in runbook.  
2. **DAO**: Add `atomic_transition_to_ingesting` and `update_resource_after_ingestion`; remove or deprecate extraction-only methods.  
3. **Ingestion service**: New `services/ingestion` with Graphiti client setup and `ingest_resource(resource_id)` implementing validate → claim → add_episode → update.  
4. **Modal worker**: Add `ingest_resource` to `modal_workers.py` with correct image and secrets; remove `extract_insights`.  
5. **Phase 3 removal**: Remove insight agent, InsightsService.extract_insights, extract_insights Modal, extraction DAO usage, insight-related config/models; update PipelineStage usage and runbook.  
6. **Verification**: Runbook steps, manual test scraped → ingesting → complete and failure cases (short content, missing content, bad Neo4j).

## Complexity Tracking

No constitution violations. Table left empty.
