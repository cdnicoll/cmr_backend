# Tasks: Phase 2b — YouTube Scraping

**Input**: Design documents from `/specs/003b-scraping-youtube/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/, quickstart.md ✓

**Tests**: Not explicitly requested in spec — no test tasks included.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `scripts/` at repository root
- Source: `src/deployment/modal_workers.py`, `src/services/scraping/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure dependencies and project structure for YouTube scraping path

- [X] T001 Verify `youtube-transcript-api` in pyproject.toml (add if missing)
- [X] T002 [P] Verify project structure: `src/deployment/modal_workers.py`, `src/services/scraping/youtube_extractor.py`, `src/services/scraping/service.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models and DAO that Phase 2b depends on (from Phase 2)

**⚠️ CRITICAL**: Phase 2 (003-scraping) must be complete. Phase 2b extends it.

- [X] T003 Verify `ScrapedContent` and `ScrapedContentMetadata` support `metadata.type: Literal["website", "youtube"]` in src/models/scraping/scraped_content.py
- [X] T004 Verify `atomic_transition_to_scraping` and `update_resource_after_scrape` exist in src/services/supabase/resources_dao.py
- [X] T005 Verify `SCRAPE_MIN_WORD_COUNT` (or `scrape_min_word_count`) in config/settings

**Checkpoint**: Foundation ready — user story implementation can begin

---

## Phase 3: User Story 1 — Scrape YouTube Resource (Priority: P1) 🎯 MVP

**Goal**: Run scrape worker with YouTube `resource_id`; transcript extracted and stored in `scraped_content`

**Independent Test**: Create resource with YouTube URL (`pipeline_stage = discovered`); spawn scrape worker; confirm `pipeline_stage` → `scraped` and `scraped_content` populated with transcript.

### Implementation for User Story 1

- [X] T006 [P] [US1] Implement video ID extraction for `youtube.com/watch?v=`, `youtu.be/`, and `youtube.com/shorts/` in src/services/scraping/youtube_extractor.py
- [X] T007 [US1] Implement transcript fetch via `youtube-transcript-api` in src/services/scraping/youtube_extractor.py — concatenate transcript `text` into markdown; title = resource URL (youtube-transcript-api does not return video title)
- [X] T008 [US1] Extend `scrape_resource` to route `type=youtube` to YouTube extraction path in src/services/scraping/service.py
- [X] T009 [US1] Implement `scraped_content` JSONB with `metadata.type = "youtube"` on success in src/services/scraping/service.py
- [X] T010 [US1] Implement word count validation: if `word_count < SCRAPE_MIN_WORD_COUNT`, mark `failed` with `failure_reason = "Insufficient content"` in src/services/scraping/service.py
- [X] T011 [US1] Handle `TranscriptsDisabled`, `VideoUnavailable`, `NoTranscriptFound` exceptions from youtube-transcript-api — mark `failed` with `failure_reason` in src/services/scraping/service.py

**Checkpoint**: User Story 1 complete — YouTube scrape path functional

---

## Phase 4: User Story 2 — Pipeline Stage Transitions (Priority: P1)

**Goal**: `pipeline_stage` reflects scrape progress; downstream workers and recovery logic can reason about resource state

**Independent Test**: Inspect resource row before/after scrape; confirm stage transitions and `updated_at` changes.

### Implementation for User Story 2

- [X] T012 [US2] Implement atomic transition `discovered` → `scraping` at scrape start in src/services/scraping/service.py (via resources_dao)
- [X] T013 [US2] Implement transition `scraping` → `scraped` on success in src/services/scraping/service.py
- [X] T014 [US2] Implement transition `scraping` → `failed` with `failure_reason` on error (disabled captions, unavailable, insufficient content) in src/services/scraping/service.py
- [X] T015 [US2] Implement skip when `pipeline_stage != discovered` (no overwrite of completed content) in src/services/scraping/service.py

**Checkpoint**: User Stories 1 and 2 complete — full YouTube scrape flow with correct stage transitions

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validation and documentation

- [X] T016 Run quickstart.md validation: create YouTube resource, spawn scrape_resource, verify scraped_content and pipeline_stage
- [X] T017 [P] Update quickstart.md if deploy or invocation steps differ from current implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 2 (003-scraping) being complete — BLOCKS user stories if not
- **User Story 1 (Phase 3)**: Depends on Foundational
- **User Story 2 (Phase 4)**: Depends on Foundational; shares service.py with US1
- **Polish (Phase 5)**: Depends on US1 and US2 complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational — core YouTube extraction
- **User Story 2 (P1)**: Can start after Foundational — pipeline transitions; implementation overlaps with US1 in service.py

### Within Each User Story

- US1: youtube_extractor before service routing; service routing before scraped_content schema
- US2: Atomic transition before success/failure transitions

### Parallel Opportunities

- T002 can run in parallel with T001
- T006 can run in parallel with other US1 tasks that don't touch youtube_extractor
- T017 can run in parallel with T016

---

## Parallel Example: User Story 1

```bash
# Video ID extraction and transcript fetch can be developed together:
Task T006: "Implement video ID extraction in src/services/scraping/youtube_extractor.py"
Task T007: "Implement transcript fetch in src/services/scraping/youtube_extractor.py"
# (T007 depends on T006 for video_id; sequential within youtube_extractor)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (verify Phase 2 artifacts)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run quickstart — create YouTube resource, spawn scrape, verify scraped_content
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test via quickstart → Deploy (MVP)
3. Add User Story 2 → Verify stage transitions → Deploy
4. Polish → Quickstart validation

### Implementation Notes

- Phase 2b extends existing `scrape_resource`; no new Modal functions
- `youtube-transcript-api` is synchronous; wrap in `run_in_executor` for async service
- Same `scraped_content` JSONB schema as Phase 2; `metadata.type = "youtube"` for YouTube path

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to user story for traceability
- Each user story independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
