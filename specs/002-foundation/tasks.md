# Tasks: Phase 1 — Foundation (Resources and Auth)

**Input**: Design documents from `/specs/002-foundation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification; no test tasks included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/`, `scripts/`, `docs/` at repository root
- Paths follow plan.md structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure for the resources domain

- [X] T001 Create resources domain directories: `src/api/routes/resources/`, `src/models/resources/`, `src/services/supabase/`, `src/api/schemas/` (if not exists), `docs/db/migrations/` (if not exists)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration and URL validation — MUST complete before batch API implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [US3] Add `resources` table migration to `scripts/migrate.py` — CREATE TABLE IF NOT EXISTS resources with id, url, title, type, pipeline_stage, failure_reason, scraped_content (JSONB), insight (JSONB), discovery_source_id (UUID), created_at, updated_at; indexes: resources_url_key (UNIQUE), resources_pipeline_stage_idx, resources_created_at_idx; CHECK constraints for pipeline_stage and type; updated_at trigger: create `update_updated_at_column()` function (CREATE OR REPLACE) if not exists, then DROP TRIGGER IF EXISTS + CREATE TRIGGER resources_updated_at BEFORE UPDATE ON resources FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
- [X] T003 [P] Implement `src/utils/url_validation.py` — SSRF protection (block localhost, 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, link-local), URL normalization (https preferred, trailing slash), type detection (website vs youtube), YouTube format validation (youtube.com/watch, youtu.be/)

**Checkpoint**: Migration runs successfully; url_validation module passes validation for valid/invalid/SSRF URLs

---

## Phase 3: User Story 1 — Create Resources via Batch API (Priority: P1) 🎯 MVP

**Goal**: `POST /api/v1/resources` accepts URLs, validates each, inserts new resources, skips duplicates; returns batch response with created/skipped/errors counts and per-URL results.

**Independent Test**: `POST /api/v1/resources` with valid URL returns 201; resource appears in Supabase `resources` table with `pipeline_stage = discovered`.

### Implementation for User Story 1

- [X] T004 [P] [US1] Create ResourceType and PipelineStage enums in `src/models/resources/resource.py`
- [X] T005 [P] [US1] Create BatchCreateResourceRequest, BatchCreateResourceResponse, ResourceResult schemas in `src/api/schemas/resources.py`
- [X] T006 [US1] Implement ResourcesDAO in `src/services/supabase/resources_dao.py` — insert resource, get by url; use `get_supabase_client()` from `src/config/supabase.py`; handle unique constraint for duplicate skip
- [X] T007 [US1] Implement ResourcesService in `src/services/resources_service.py` — batch_create: validate each URL via url_validation, call DAO for insert/lookup, return BatchCreateResourceResponse with created/skipped/errors and results
- [X] T008 [US1] Add `get_resources_service()` in `src/api/dependencies.py` and implement `POST /api/v1/resources` route in `src/api/routes/resources/router.py` — use `Depends(get_validated_jwt_user)`, `Depends(get_resources_service)`; return 201 if any created, 200 if all skipped; handle 422 for validation errors
- [X] T009 [US1] Register resources router under `/api/v1` prefix in `src/api/main.py`

**Checkpoint**: User Story 1 fully functional — batch create works; duplicates skipped; invalid/SSRF URLs return 422

---

## Phase 4: User Story 2 — Auth Protection (Priority: P1)

**Goal**: Protected endpoints require valid JWT; unauthenticated requests receive 401.

**Independent Test**: Hit `POST /api/v1/resources` without JWT — confirm 401.

### Implementation for User Story 2

- [X] T010 [US2] Verify `POST /api/v1/resources` uses `Depends(get_validated_jwt_user)` in `src/api/routes/resources/router.py` — auth is satisfied by T008; this task confirms and documents

**Checkpoint**: User Story 2 verified — 401 returned for missing/invalid JWT

---

## Phase 5: User Story 3 — Bootstrap Resource Schema (Priority: P1)

**Goal**: Migration creates `resources` table idempotently; developer can run `uv run python scripts/migrate.py` and have schema ready.

**Independent Test**: Run migration script; verify `resources` table exists with expected columns.

### Implementation for User Story 3

- [X] T011 [US3] Verify migration idempotency — run `scripts/migrate.py` twice; confirm no error on second run; document in `specs/002-foundation/quickstart.md` if needed

**Checkpoint**: User Story 3 verified — migration idempotent; schema matches data-model.md

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [X] T012 Run quickstart.md validation — follow `specs/002-foundation/quickstart.md` steps; confirm all checklist items pass
- [X] T013 [P] Add request_id to ResourcesService log messages per `src/utils/logging.py` conventions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS User Stories 1 and 2
- **User Story 1 (Phase 3)**: Depends on Foundational — migration and url_validation must exist
- **User Story 2 (Phase 4)**: Satisfied by User Story 1 implementation (route uses Depends)
- **User Story 3 (Phase 5)**: Migration in Phase 2; verification only
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Requires Phase 2 (migration, url_validation)
- **User Story 2 (P1)**: Satisfied by US1 route implementation
- **User Story 3 (P1)**: Migration in Phase 2; independent verification

### Within Phase 3 (US1)

- T004, T005 can run in parallel (models, schemas)
- T006 depends on T004 (DAO uses enums)
- T007 depends on T003, T006 (service uses url_validation, DAO)
- T008 depends on T005, T007 (route uses schemas, service)
- T009 depends on T008 (register router)

### Parallel Opportunities

- T002 and T003 can run in parallel (migration vs url_validation)
- T004 and T005 can run in parallel (models vs schemas)
- T013 can run anytime after T007

---

## Parallel Example: Phase 2

```bash
# Launch foundational tasks in parallel:
Task T002: "Add resources table migration to scripts/migrate.py"
Task T003: "Implement url_validation.py"
```

---

## Parallel Example: User Story 1

```bash
# Launch models and schemas together:
Task T004: "Create ResourceType and PipelineStage enums in src/models/resources/resource.py"
Task T005: "Create BatchCreateResourceRequest, BatchCreateResourceResponse, ResourceResult in src/api/schemas/resources.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (T002, T003)
3. Complete Phase 3: User Story 1 (T004–T009)
4. **STOP and VALIDATE**: Run quickstart checklist; test batch create, duplicate skip, 422 for invalid URL
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Migration and URL validation ready
2. Add User Story 1 → Batch API functional → Deploy (MVP)
3. User Stories 2 & 3 are verification — already satisfied by implementation
4. Polish → Quickstart validation

### Suggested Order

1. T001 (Setup)
2. T002, T003 (Foundational — parallel if desired)
3. T004, T005 (parallel)
4. T006 (DAO)
5. T007 (Service)
6. T008 (Route)
7. T009 (Register)
8. T010, T011 (Verification)
9. T012, T013 (Polish)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to user story for traceability
- No test tasks — spec does not explicitly request tests
- Commit after each task or logical group
- Stop at Phase 3 checkpoint to validate MVP before continuing
