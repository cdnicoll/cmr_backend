# Tasks: Phase 3 — Insights (AI Extraction)

**Input**: Design documents from `/specs/004-insights/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec; no test tasks included.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single project: `src/`, `tests/` at repository root
- Per plan.md: `src/deployment/`, `src/services/insights/`, `src/models/insights/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and configuration for insight extraction

- [X] T001 Add `pydantic-ai==1.0.5` and `openai` to pyproject.toml
- [X] T002 Add `MODEL_INSIGHT_EXTRACTION`, `INSIGHT_MIN_WORD_COUNT`, and `INSIGHT_STUCK_TIMEOUT_MINUTES` to Settings in `src/models/config.py`
- [X] T003 [P] Add `MODEL_INSIGHT_EXTRACTION` and `OPENAI_API_KEY` to `.env`; add both to `push_modal_secrets()` in `deploy.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models and DAO extensions that MUST be complete before the insight worker can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Create `src/models/insights/__init__.py` and `src/services/insights/__init__.py`
- [X] T005 [P] Create ResourceAnalysis Pydantic models (`ScoreDimension`, `InsightScores`, `ResourceOverview`, `ResourceInsight`, `Entity`, `Relationship`, `TemporalContext`, `ResourceAnalysis`) in `src/models/insights/resource_analysis.py` per data-model.md
- [X] T006 Extend `ResourcesDAO` with `atomic_transition_to_extracting` method: `UPDATE pipeline_stage = 'extracting' WHERE id = $1 AND pipeline_stage = 'scraped' RETURNING *`; return row count so callers can detect when another worker has already claimed the resource — in `src/services/supabase/resources_dao.py`
- [X] T007 Extend `ResourcesDAO` with `update_resource_after_extraction` method to set `pipeline_stage`, `insight` (JSONB), and `failure_reason` in `src/services/supabase/resources_dao.py`

**Checkpoint**: Foundation ready — insight worker implementation can begin

---

## Phase 3: User Story 1 — Extract Insights from Scraped Resource (Priority: P1) 🎯 MVP

**Goal**: Run the insight extraction worker with a `resource_id`; entities, relationships, and scored insights are extracted and stored in the `insight` JSONB column.

**Independent Test**: Spawn insight worker with a resource in `scraped` stage; confirm `pipeline_stage` → `extracted` and `insight` populated.

### Implementation for User Story 1

- [ ] T008 [P] [US1] Create PydanticAI insight agent with `ResourceAnalysis` output schema and mining industry system prompt in `src/services/insights/agent.py`; initialise with `MODEL_INSIGHT_EXTRACTION` env var; module-level singleton
- [ ] T009 [US1] Implement `InsightsService.extract_insights(resource_id)` in `src/services/insights/service.py` covering the full flow: fetch resource → check `pipeline_stage == scraped` (skip if not, log reason) → validate `scraped_content` non-null → check `word_count >= INSIGHT_MIN_WORD_COUNT` (mark `failed` if not) → atomic transition to `extracting` (skip if 0 rows updated) → run agent → on success set `pipeline_stage = extracted` and write `insight` JSONB → on any exception set `pipeline_stage = failed` and populate `failure_reason = "{ExceptionType}: {message}"`; include structured logging for all stage transitions and skip paths
- [ ] T010 [US1] Add `extract_insights` Modal function in LLM tier in `src/deployment/modal_workers.py` with `image=image, timeout=600, cpu=1, memory=1024, retries=1, secrets=_secrets` per contracts/insight-extraction-worker.md

**Checkpoint**: User Story 1 complete — spawn `extract_insights` with `resource_id`; resource transitions to `extracted` with `insight` populated

---

## Phase 4: User Story 3 — Atomic Selection (Priority: P2)

**Goal**: Prevent race conditions when multiple workers target the same resource.

**Independent Test**: Spawn multiple workers for the same resource; confirm only one succeeds. Stuck reset is Phase 8.

### Implementation for User Story 3

- [ ] T011 [US3] Manually verify race prevention: set a resource to `extracting` directly in Supabase, invoke `extract_insights` — confirm it logs "already claimed" and returns without overwriting

**Checkpoint**: User Story 3 complete — atomic selection prevents double-processing; `INSIGHT_STUCK_TIMEOUT_MINUTES` config in place for Phase 8

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validation

- [ ] T012 Run quickstart.md validation: deploy workers, spawn `extract_insights` with test resource, verify `insight` populated, confirm no `alignment` field, confirm failure path works on short content

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — MVP
- **User Story 3 (Phase 4)**: Depends on US1 — atomic verification
- **Polish (Phase 5)**: Depends on all user stories

### Within Each User Story

- Models (T005) before DAO (T006, T007)
- Agent (T008) and DAO (T006, T007) before Service (T009)
- Service (T009) before Modal function (T010)

### Parallel Opportunities

- T003 (deploy.py), T004 (__init__.py), T005 (models) can all run in parallel with T001, T002
- T008 (agent) can run in parallel with T006, T007 once Foundational is unblocked

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Spawn `extract_insights` with resource in `scraped` stage; confirm `extracted` and `insight` populated
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy (MVP)
3. Add User Story 3 → Atomic verification
4. Polish → Quickstart validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to user story for traceability
- No test tasks — spec does not request TDD or explicit tests
- Logging and `failure_reason` handling are part of T009 (service) — not separate tasks
- Stuck-processing recovery is Phase 8; Phase 3 only documents `INSIGHT_STUCK_TIMEOUT_MINUTES`
- Commit after each task or logical group
