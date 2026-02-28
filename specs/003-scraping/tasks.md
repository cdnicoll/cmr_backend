# Tasks: Phase 2 — Scraping (Crawl4AI Integration)

**Input**: Design documents from `/specs/003-scraping/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec — no test tasks included.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single project: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and configuration for scraping

- [X] T001 Add crawl4ai and youtube-transcript-api to pyproject.toml dependencies
- [X] T002 Add SCRAPE_MIN_WORD_COUNT (optional, default 50) to Settings in src/models/config.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models and DAO extensions that MUST be complete before scrape implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Create ScrapedContent and ScrapedContentMetadata Pydantic models in src/models/scraping/scraped_content.py per data-model.md
- [X] T004 [P] Create src/models/scraping/__init__.py
- [X] T005 Extend ResourcesDAO with get_resource_by_id in src/services/supabase/resources_dao.py
- [X] T006 Extend ResourcesDAO with atomic_transition_to_scraping(resource_id) — updates pipeline_stage to scraping only where pipeline_stage=discovered; returns row count
- [X] T007 Extend ResourcesDAO with update_resource_after_scrape(resource_id, pipeline_stage, scraped_content=None, failure_reason=None) in src/services/supabase/resources_dao.py

**Checkpoint**: Foundation ready — scrape implementation can begin

---

## Phase 3: User Story 1 — Scrape Website Resource (Priority: P1) 🎯 MVP

**Goal**: Run scrape worker with resource_id; extract website or YouTube content; store in scraped_content; transition pipeline_stage. Handle blocks, insufficient content, and skip non-discovered.

**Independent Test**: Spawn scrape worker with resource in discovered stage; confirm pipeline_stage → scraped and scraped_content populated. Repeat with YouTube URL. Test blocked URL and near-empty content → failed.

### Implementation for User Story 1

- [X] T008 [P] [US1] Create Crawl4AI client wrapper (AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode.BYPASS) in src/services/scraping/crawl4ai_client.py
- [X] T009 [P] [US1] Create YouTube transcript extractor using youtube-transcript-api in src/services/scraping/youtube_extractor.py
- [X] T010 [US1] Create src/services/scraping/__init__.py and ScrapingService in src/services/scraping/service.py — orchestrate fetch, route by type, extract, validate word_count, update resource
- [X] T011 [US1] Implement minimum content length validation in ScrapingService (word_count < SCRAPE_MIN_WORD_COUNT → failed with "Insufficient content")
- [X] T012 [US1] Implement eligibility check in ScrapingService — skip if pipeline_stage != discovered; log and return
- [X] T013 [US1] Create browser_image in src/deployment/modal_workers.py with crawl4ai, playwright (extends base image)
- [X] T014 [US1] Add scrape_resource Modal function with browser_image, timeout=300, cpu=2, memory=2048, retries=1, secrets; invoke ScrapingService.scrape_resource(resource_id)

**Checkpoint**: User Story 1 complete — scrape worker functional for website and YouTube

---

## Phase 4: User Story 2 — Pipeline Stage Transitions (Priority: P1)

**Goal**: Ensure pipeline_stage transitions atomically (discovered→scraping at start) and failure_reason populated on all failure paths.

**Independent Test**: Inspect resource row before/after scrape; confirm stage transitions and updated_at. Verify failed resources have failure_reason.

### Implementation for User Story 2

- [X] T015 [US2] Ensure atomic transition discovered→scraping at scrape start in ScrapingService — use atomic_transition_to_scraping; if 0 rows updated, log and return (another worker claimed)
- [X] T016 [US2] Ensure failure_reason populated on all failure paths in ScrapingService — Crawl4AI/YouTube exception, insufficient content, eligibility skip (no update needed for skip)

**Checkpoint**: Pipeline transitions and failure handling verified

---

## Phase 5: User Story 3 — Timeouts and Retries (Priority: P2)

**Goal**: Modal retries=1 on scrape function; document timeout behavior.

**Independent Test**: Spawn against slow/blocking URL; confirm failure handling. Verify retries=1 in decorator.

### Implementation for User Story 3

- [X] T017 [US3] Confirm retries=1 on scrape_resource Modal decorator in src/deployment/modal_workers.py
- [X] T018 [US3] Add structured logging in ScrapingService for resource_id, stage transitions, and failures (use get_logger)

**Checkpoint**: Timeouts and retries configured; logging in place

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Configuration, documentation, validation

- [X] T019 Add SCRAPE_MIN_WORD_COUNT to .env.example (optional, default 50)
- [ ] T020 Run quickstart.md validation — deploy, create resource, spawn scrape, verify Supabase

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational
- **User Story 2 (Phase 4)**: Depends on User Story 1 (transitions are in ScrapingService)
- **User Story 3 (Phase 5)**: Depends on User Story 1 (decorator on scrape_resource)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — Core scrape implementation
- **User Story 2 (P1)**: Embedded in US1 implementation; Phase 4 tasks verify/enforce
- **User Story 3 (P2)**: Small addition to scrape_resource; can be done with US1

### Within Each User Story

- Models (ScrapedContent) before services
- DAO extensions before ScrapingService
- Crawl4AI client and YouTube extractor before ScrapingService
- ScrapingService before Modal function

### Parallel Opportunities

- T003, T004 can run in parallel
- T008, T009 can run in parallel (Crawl4AI client vs YouTube extractor)
- T019 can run anytime after T002

---

## Parallel Example: User Story 1

```bash
# Launch Crawl4AI client and YouTube extractor together:
Task T008: "Create Crawl4AI client wrapper in src/services/scraping/crawl4ai_client.py"
Task T009: "Create YouTube transcript extractor in src/services/scraping/youtube_extractor.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Spawn scrape worker with resource_id; verify in Supabase
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. User Story 1 → Test scrape for website + YouTube (MVP)
3. User Story 2 → Verify transitions (likely already done in US1)
4. User Story 3 → Add retries=1, logging
5. Polish → quickstart validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- scrape_resource is a standalone Modal function — not a job type; invoked via Modal CLI or spawn
- Phase 1 (Resources) must be complete — resources table with pipeline_stage, scraped_content, failure_reason
- No tests requested in spec — omit for now; add later if needed
