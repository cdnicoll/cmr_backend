# Tasks: Knowledge Graph Ingestion from Scraped Content

**Input**: Design documents from `specs/005-graphiti-ingestion/`  
**Prerequisites**: plan.md, spec.md  
**Tests**: Not requested in spec; runbook-driven manual verification only.

**Organization**: Tasks are grouped by user story to allow independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Repository root: `src/`, `docs/`, `tests/`
- Single backend; Modal workers in `src/deployment/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add dependency and package structure for ingestion.

- [X] T001 [P] Add graphiti-core (and optional LLM extras if not using OpenAI) to dependencies in pyproject.toml
- [X] T002 [P] Create src/services/ingestion/ package with __init__.py per plan structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, secrets, and DAO that the ingestion worker depends on. No user story implementation until this phase is complete.

- [X] T003 [P] Add ingest_min_word_count (INGEST_MIN_WORD_COUNT, default 100) and ingest_stuck_timeout_minutes (INGEST_STUCK_TIMEOUT_MINUTES, default 30) to Settings in src/models/config.py
- [X] T004 [P] Add Neo4j and LLM env vars (neo4j_uri, neo4j_username, neo4j_password, neo4j_database; openai_api_key or equivalent for Graphiti) to Settings in src/models/config.py
- [X] T005 Update push_modal_secrets in src/deployment/deploy.py to include INGEST_MIN_WORD_COUNT, INGEST_STUCK_TIMEOUT_MINUTES, Neo4j vars, and LLM/embedder vars for ingestion worker
- [X] T006 [P] Add atomic_transition_to_ingesting(resource_id: str) -> int in src/services/supabase/resources_dao.py (UPDATE pipeline_stage = 'ingesting' WHERE id = $1 AND pipeline_stage = 'scraped'; return row count)
- [X] T007 [P] Add update_resource_after_ingestion(resource_id, pipeline_stage, failure_reason=None) in src/services/supabase/resources_dao.py (set pipeline_stage and optionally failure_reason; no insight)
- [X] T008 [P] Update .env.example with INGEST_MIN_WORD_COUNT, INGEST_STUCK_TIMEOUT_MINUTES, NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE, OPENAI_API_KEY (or equivalent) for ingestion

**Checkpoint**: Foundation ready — ingestion service and Modal worker can be implemented.

---

## Phase 3: User Story 1 — Ingest Scraped Content into the Knowledge Graph (Priority: P1) — MVP

**Goal**: Operator triggers ingestion for a scraped resource; system validates content, transitions to ingesting, sends text to Graphiti as episode, sets pipeline_stage to complete or failed.

**Independent Test**: Run `modal run src.deployment.modal_workers::ingest_resource --resource-id <uuid>` for a resource in scraped stage with valid scraped_content; confirm resource transitions to complete and graph reflects ingested content.

### Implementation for User Story 1

- [X] T009 [US1] Implement ingest_resource(resource_id) in src/services/ingestion/service.py: load resource via get_resource_by_id; require pipeline_stage == scraped and non-null scraped_content; validate word count >= ingest_min_word_count (else set failed and return per T012); call atomic_transition_to_ingesting — if 0 rows updated (already claimed or not scraped), log and return without calling Graphiti or updating resource; build episode (name e.g. resource_{id}, episode_body=markdown, source=EpisodeType.text, source_description=url/title, reference_time=resource updated_at/created_at); call Graphiti add_episode; on success call update_resource_after_ingestion(complete, failure_reason=None); on exception call update_resource_after_ingestion(failed, failure_reason)
- [X] T010 [US1] Add Graphiti client initialization from env (NEO4J_*, LLM vars) and structured logging (get_logger) in src/services/ingestion/service.py
- [X] T011 [US1] Add ingest_resource(resource_id: str) Modal function in src/deployment/modal_workers.py with image that includes graphiti-core, secrets including Neo4j and LLM, timeout 600s, and invoke ingestion service ingest_resource

**Checkpoint**: User Story 1 is testable — trigger worker for scraped resource and verify complete + graph updated.

---

## Phase 4: User Story 2 — Validate Content and Record Failures (Priority: P2)

**Goal**: Resources with missing or below-threshold content are marked failed with a reason; Graphiti/connection failures set failure_reason so operators can diagnose without logs only.

**Independent Test**: Run ingestion worker for resource with very short or missing scraped_content; confirm pipeline_stage = failed and failure_reason set. Simulate Graphiti/Neo4j failure and confirm failure_reason stored.

### Implementation for User Story 2

- [X] T012 [US2] Ensure validation path in src/services/ingestion/service.py: when scraped_content missing or word count < ingest_min_word_count, call update_resource_after_ingestion(resource_id, failed, failure_reason="Insufficient content for ingestion" or similar) and return without calling Graphiti
- [X] T013 [US2] Ensure exception path in src/services/ingestion/service.py: wrap Graphiti add_episode in try/except; on exception call update_resource_after_ingestion(resource_id, failed, failure_reason=f"{type(e).__name__}: {str(e)}")
- [X] T014 [US2] Ensure success path clears failure_reason in src/services/ingestion/service.py by calling update_resource_after_ingestion(resource_id, complete, failure_reason=None)

**Checkpoint**: User Story 2 verified — validation and service failures record failure_reason; success clears it.

---

## Phase 5: User Story 3 — Single Pipeline Path and Removal of Old Extraction (Priority: P3)

**Goal**: Pipeline is scraped → ingesting → complete only; Phase 3 extraction code and runbook references removed.

**Independent Test**: Confirm no extract_insights Modal function; no code transitions to extracting/extracted; runbook describes only ingest flow.

### Implementation for User Story 3

- [X] T015 [P] [US3] Remove extract_insights(resource_id) Modal function from src/deployment/modal_workers.py
- [X] T016 [P] [US3] Remove InsightsService.extract_insights and extract_insights call; remove or gut src/services/insights/agent.py and extract_insights logic from src/services/insights/service.py
- [X] T017 [P] [US3] Remove atomic_transition_to_extracting and update_resource_after_extraction from src/services/supabase/resources_dao.py and remove all imports/call sites (e.g. from insights service)
- [X] T018 [P] [US3] Remove insight_min_word_count, insight_stuck_timeout_minutes, model_insight_extraction (and OPENROUTER if only used for insights) from src/models/config.py
- [X] T019 [P] [US3] Remove insight-related vars from app-config in push_modal_secrets in src/deployment/deploy.py
- [X] T020 [P] [US3] Remove EXTRACTING and EXTRACTED from PipelineStage enum in src/models/resources/resource.py (or leave enum values but ensure no code transitions to them)
- [X] T021 [US3] Replace "Insight extraction (Phase 3)" section with "Ingest to Graphiti" in docs/runbook.md: command `modal run src.deployment.modal_workers::ingest_resource --resource-id <uuid>`, verify scraped → ingesting → complete, document failure cases (validation, Neo4j/Graphiti errors); add INGEST_* and Neo4j/LLM env vars to runbook if not already in .env.example

**Checkpoint**: Single path only; runbook and codebase describe only scraped → ingesting → complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and verification.

- [X] T022 [P] Verify .env.example and docs/runbook.md list all ingestion-related env vars (INGEST_MIN_WORD_COUNT, INGEST_STUCK_TIMEOUT_MINUTES, NEO4J_*, OPENAI_API_KEY or equivalent)
- [ ] T023 Run runbook verification: manually test scraped → ingesting → complete with a real resource; test short-content and missing-content failure paths; confirm failure_reason in DB

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1. Blocks Phases 3–5.
- **Phase 3 (US1)**: Depends on Phase 2. Delivers MVP (ingest worker).
- **Phase 4 (US2)**: Depends on Phase 3 (same service file). Completes validation and failure_reason behavior.
- **Phase 5 (US3)**: Depends on Phase 2 (config/DAO used by removal). Can be done in parallel with Phase 3/4 if removal is isolated; safer after US1/US2 done.
- **Phase 6 (Polish)**: Depends on Phases 3–5.

### User Story Dependencies

- **US1 (P1)**: After Phase 2. No dependency on US2/US3.
- **US2 (P2)**: After US1 (same ingestion service). Adds validation and failure-reason guarantees.
- **US3 (P3)**: Can start after Phase 2 for removal tasks (T015–T020); T021 (runbook) should follow so runbook reflects final flow.

### Parallel Opportunities

- Phase 1: T001, T002 [P].
- Phase 2: T003, T004, T006, T007, T008 [P]; T005 after config.
- Phase 5: T015–T020 [P] (different files).
- Phase 6: T022 [P].

---

## Parallel Example: Phase 2

```text
# Config and DAO in parallel:
T003: Add INGEST_* to src/models/config.py
T004: Add Neo4j/LLM to src/models/config.py
T006: Add atomic_transition_to_ingesting in resources_dao.py
T007: Add update_resource_after_ingestion in resources_dao.py
T008: Update .env.example
# Then T005: Update deploy.py (depends on config).
```

## Parallel Example: User Story 3

```text
# Removal tasks in parallel (different files):
T015: Remove extract_insights from modal_workers.py
T016: Gut insights/agent and service
T017: Remove extraction DAO methods
T018: Remove insight_* from config.py
T019: Remove insight vars from deploy.py
T020: Remove EXTRACTING/EXTRACTED from PipelineStage
# Then T021: Runbook update (single file).
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational).
3. Complete Phase 3 (US1): ingestion service + Modal ingest_resource.
4. **Validate**: Run worker for a scraped resource; confirm complete and graph updated.
5. Deploy/demo if ready.

### Incremental Delivery

1. Phase 1 + 2 → foundation.
2. Phase 3 (US1) → test independently (MVP).
3. Phase 4 (US2) → validate failure paths and failure_reason.
4. Phase 5 (US3) → remove Phase 3 code and update runbook.
5. Phase 6 → runbook and manual verification.

### Task Count Summary

| Phase        | Story | Task IDs   | Count |
|-------------|-------|------------|-------|
| Setup       | —     | T001–T002  | 2     |
| Foundational| —     | T003–T008  | 6     |
| US1 (P1)    | US1   | T009–T011  | 3     |
| US2 (P2)    | US2   | T012–T014  | 3     |
| US3 (P3)    | US3   | T015–T021  | 7     |
| Polish      | —     | T022–T023  | 2     |
| **Total**   |       |            | **23**|

---

## Notes

- [P] = safe to run in parallel with other [P] tasks in the same phase (different files or no shared state).
- [USn] maps task to spec user story for traceability.
- No automated test tasks; verification is runbook-driven (T023).
- Commit after each task or logical group; stop at any checkpoint to validate that story.
- **Optional after T016**: If no other code uses `pydantic-ai` or `openai`, remove them from `pyproject.toml` to drop unused Phase 3 extraction dependencies.
