# Implementation Plan: Phase 1 — Foundation (Resources and Auth)

**Branch**: `002-foundation` | **Date**: 2025-02-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-foundation/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add the **Resources** domain: `resources` table, batch creation API (`POST /api/v1/resources`), URL validation (SSRF protection, normalization, type detection), and duplicate handling. Auth uses the starter kit's Supabase JWT as-is. Migration creates `resources` table with `pipeline_stage`, `failure_reason`, `scraped_content`, `insight`, and `discovery_source_id`. Extends the existing starter application (001-starter-application) without replacing it.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Supabase, Pydantic, pydantic-settings (per starter)  
**Storage**: Supabase (PostgreSQL) — `resources` table via Supabase client or asyncpg  
**Testing**: pytest (unit, integration, contract)  
**Target Platform**: Linux server (Modal), local dev via uvicorn  
**Project Type**: web-service (REST API)  
**Performance Goals**: Stateless API; batch creation handles moderate URL volumes  
**Constraints**: 10-minute setup preserved; URL validation must block SSRF; no API key system  
**Scale/Scope**: Phase 1 only — Resources + Auth; no scraping, insights, or discovery  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify alignment with `.specify/memory/constitution.md`:

- **Quick Start**: Setup path remains under 10 minutes; migration adds `resources` table; no new undocumented prerequisites
- **REST API**: Health check and API docs present (starter); new `POST /api/v1/resources` documented
- **Cloud-Ready**: Stateless; Modal deployment path unchanged
- **Observability**: X-Request-ID, structured logging in place (starter)
- **Developer Guidance**: Patterns in `_local/starter-kit/`; Resources follows Service → DAO pattern

**Gate**: PASS — extends starter; no new violations.

**Post–Phase 1 re-check**: PASS — data-model.md, contracts/, quickstart.md align with Constitution.

## Project Structure

### Documentation (this feature)

```text
specs/002-foundation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (resources-api.md)
└── tasks.md             # Phase 2 output (/speckit.tasks - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── api/
│   ├── main.py               # Register /api/v1/resources router
│   ├── routes/
│   │   └── resources/
│   │       └── router.py     # POST /api/v1/resources
│   └── schemas/
│       └── resources.py     # BatchCreateRequest, BatchCreateResponse
├── services/
│   ├── resources_service.py  # ResourcesService (orchestration)
│   └── supabase/
│       └── resources_dao.py  # ResourcesDAO (CRUD)
├── utils/
│   └── url_validation.py     # SSRF, normalize, type detection
└── models/
    └── resources/
        └── resource.py       # ResourceType, PipelineStage enums

docs/db/migrations/
└── 002_resources.sql         # resources table (or extend migrate.py)
```

**Structure Decision**: Single-project layout. Resources domain added alongside existing jobs domain. New route under `/api/v1/resources`; Service → DAO per starter-kit patterns.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
