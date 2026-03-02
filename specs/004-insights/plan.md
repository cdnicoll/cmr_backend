# Implementation Plan: Phase 3 — Insights (AI Extraction)

**Branch**: `004-insights` | **Date**: 2025-03-01 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/004-insights/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Implement **AI-powered insight extraction** from scraped content. A Modal function `extract_insights(resource_id)` reads `scraped_content` from the resource, runs a PydanticAI agent to extract entities, relationships, and scored insights, and stores the result in `insight` JSONB. Transitions `pipeline_stage` from `scraped` → `extracting` → `extracted` (or `failed`). Runs in the LLM tier. No REST endpoint; invoked via Modal CLI/dashboard or by pipeline orchestration in Phase 8.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: PydanticAI, OpenAI (or configured provider), Supabase, Modal, asyncpg (per starter)  
**Storage**: Supabase (PostgreSQL) — `resources` table; `insight` JSONB column (existing from Phase 1)  
**Testing**: pytest (unit, integration)  
**Target Platform**: Modal (LLM tier), Linux  
**Project Type**: web-service (backend worker)  
**Performance Goals**: 5 min timeout per resource; agent produces structured output  
**Constraints**: LLM tier; `MODEL_INSIGHT_EXTRACTION` env var required; episode size for Graphiti (<400 chars)  
**Scale/Scope**: Phase 3 only — Insights; no graph ingestion, discovery, or orchestration

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify alignment with `.specify/memory/constitution.md`:

- **Quick Start**: Setup path remains under 10 minutes; PydanticAI + model env add to Modal image; local dev may skip insight worker
- **REST API**: Health check and API docs unchanged (starter); no new REST endpoints in Phase 3
- **Cloud-Ready**: Stateless worker; Modal deployment path unchanged
- **Observability**: X-Request-ID, structured logging; insight worker logs resource_id, stage transitions
- **Developer Guidance**: Patterns in `_local/starter-kit/`; insight follows Modal worker conventions

**Gate**: PASS — extends starter; no new violations.

**Post–Phase 1 re-check**: PASS — data-model.md, contracts/, quickstart.md align with Constitution.

## Project Structure

### Documentation (this feature)

```text
specs/004-insights/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (insight-extraction-worker.md)
└── tasks.md             # Phase 2 output (/speckit.tasks - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── deployment/
│   └── modal_workers.py       # Add extract_insights function; LLM tier
├── services/
│   ├── insights/
│   │   ├── __init__.py
│   │   ├── service.py        # InsightsService (orchestration)
│   │   └── agent.py          # PydanticAI insight agent
│   └── supabase/
│       └── resources_dao.py  # Extend: atomic scraped→extracting, update insight, failure_reason
└── models/
    └── insights/
        └── resource_analysis.py # ResourceAnalysis schema (Pydantic) for agent output
```

**Structure Decision**: Single-project layout. Insights domain added alongside scraping. Modal function `extract_insights` is standalone (not a job type); invoked directly. Service → DAO per starter-kit; PydanticAI agent isolated for testability.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
