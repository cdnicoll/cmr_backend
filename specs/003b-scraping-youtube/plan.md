# Implementation Plan: Phase 2b — YouTube Scraping

**Branch**: `003b-scraping-youtube` | **Date**: 2025-02-27 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `/specs/003b-scraping-youtube/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Extend the existing `scrape_resource` Modal function to handle `type = youtube` resources using `youtube-transcript-api`. Crawl4AI does not support YouTube. The extraction path, `scraped_content` JSONB schema, `pipeline_stage` transitions, and failure handling are identical to Phase 2 — only the extraction library differs. No new tables, no new Modal functions.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: youtube-transcript-api, Supabase, Modal (existing from Phase 2)  
**Storage**: Supabase (PostgreSQL) — `resources` table; `scraped_content` JSONB column (existing)  
**Testing**: pytest (unit, integration)  
**Target Platform**: Modal (browser tier or base tier — YouTube path does not require browser)  
**Project Type**: web-service (backend worker)  
**Performance Goals**: 5 min timeout per resource; YouTube transcript API is lightweight  
**Constraints**: Same `scrape_resource` function; extends Phase 2 implementation  
**Scale/Scope**: Phase 2b only — YouTube path only; no discovery, insights, or graph

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify alignment with `.specify/memory/constitution.md`:

- **Quick Start**: Setup path unchanged; `youtube-transcript-api` already in Phase 2 dependencies; local dev may skip scrape worker
- **REST API**: Health check and API docs unchanged (starter); no new REST endpoints in Phase 2b
- **Cloud-Ready**: Stateless worker; Modal deployment path unchanged
- **Observability**: X-Request-ID, structured logging; scrape worker logs resource_id, stage transitions
- **Developer Guidance**: Patterns in `_local/starter-kit/`; scrape follows Modal worker conventions

**Gate**: PASS — extends Phase 2; no new violations.

**Post–Phase 1 re-check**: PASS — data-model.md, contracts/, quickstart.md align with Constitution.

## Project Structure

### Documentation (this feature)

```text
specs/003b-scraping-youtube/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (scrape-worker-youtube.md)
└── tasks.md             # Phase 2 output (/speckit.tasks - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── deployment/
│   └── modal_workers.py       # Extend scrape_resource; route type=youtube to YouTube path
└── services/
    └── scraping/
        └── youtube_extractor.py  # YouTube transcript extraction (extend or create)
```

**Structure Decision**: No new files required if Phase 2 already includes `youtube_extractor.py`. Phase 2b extends the existing `scrape_resource` routing logic and ensures `youtube_extractor.py` handles all edge cases (disabled captions, insufficient content). Single-project layout; no new domain.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
