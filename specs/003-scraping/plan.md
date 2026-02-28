# Implementation Plan: Phase 2 — Scraping (Crawl4AI Integration)

**Branch**: `003-scraping` | **Date**: 2025-02-27 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/003-scraping/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Integrate **Crawl4AI** for web content extraction. A Modal scrape function accepts `resource_id`, fetches the resource, routes by type (website vs YouTube), runs Crawl4AI (or YouTube extraction), stores raw content in `scraped_content` JSONB, and transitions `pipeline_stage` from `discovered` → `scraping` → `scraped` (or `failed`). Runs in the browser tier. No REST endpoint; invoked via Modal CLI/dashboard or by discovery in Phase 5.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Crawl4AI, Supabase, Modal, asyncpg (per starter)  
**Storage**: Supabase (PostgreSQL) — `resources` table; `scraped_content` JSONB column (existing from Phase 1)  
**Testing**: pytest (unit, integration)  
**Target Platform**: Modal (browser tier), Linux  
**Project Type**: web-service (backend worker)  
**Performance Goals**: 5 min timeout per resource; Crawl4AI handles dynamic pages  
**Constraints**: Browser tier requires Playwright/Chromium; Crawl4AI uses headless browser  
**Scale/Scope**: Phase 2 only — Scraping; no discovery, insights, or graph

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify alignment with `.specify/memory/constitution.md`:

- **Quick Start**: Setup path remains under 10 minutes; Crawl4AI + browser deps add to Modal image only; local dev may skip scrape worker
- **REST API**: Health check and API docs unchanged (starter); no new REST endpoints in Phase 2
- **Cloud-Ready**: Stateless worker; Modal deployment path unchanged
- **Observability**: X-Request-ID, structured logging; scrape worker logs resource_id, stage transitions
- **Developer Guidance**: Patterns in `_local/starter-kit/`; scrape follows Modal worker conventions

**Gate**: PASS — extends starter; no new violations.

**Post–Phase 1 re-check**: PASS — data-model.md, contracts/, quickstart.md align with Constitution.

## Project Structure

### Documentation (this feature)

```text
specs/003-scraping/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (scrape-worker.md)
└── tasks.md             # Phase 2 output (/speckit.tasks - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── deployment/
│   └── modal_workers.py       # Add scrape_resource function; extend browser image for Crawl4AI
├── services/
│   ├── scraping/
│   │   ├── __init__.py
│   │   ├── service.py        # ScrapingService (orchestration)
│   │   └── crawl4ai_client.py # Crawl4AI wrapper (website path)
│   └── supabase/
│       └── resources_dao.py  # Extend: update pipeline_stage, scraped_content, failure_reason
└── models/
    └── scraping/
        └── scraped_content.py # ScrapedContent schema (Pydantic) for JSONB structure
```

**Structure Decision**: Single-project layout. Scraping domain added alongside resources. Modal function `scrape_resource` is standalone (not a job type); invoked directly. Service → DAO per starter-kit; Crawl4AI client isolated for testability.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
