# Tasks: Pipeline Orchestration and Recovery

**Input**: Design documents from `specs/001-pipeline-orchestration-recovery/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Optional unit test for recovery logic (plan); no tests explicitly requested in spec. Runbook and quickstart used for verification.

**Organization**: Tasks grouped by user story so each story can be implemented and verified independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Config Cleanup)

**Purpose**: Remove job-queue config; pipeline uses only resource stages.

- [x] T001 [P] Remove `job_stuck_timeout_minutes` and `JOB_STUCK_TIMEOUT_MINUTES` from `src/models/config.py` (job queue dropped; recovery uses resource timeouts only)
- [x] T002 [P] Remove `JOB_STUCK_TIMEOUT_MINUTES` from Modal app-config secret push in `src/deployment/deploy.py` (e.g. in `push_modal_secrets()` or equivalent)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config and DAO support required for recovery (US2) and re-queue (US3). No user story implementation before this completes.

- [x] T003 [P] Add `scrape_stuck_timeout_minutes` to Settings in `src/models/config.py` with `validation_alias="SCRAPE_STUCK_TIMEOUT_MINUTES"` and default 15; ensure `ingest_stuck_timeout_minutes` remains (INGEST_STUCK_TIMEOUT_MINUTES)
- [x] T004 [P] Add `list_stuck_resources(pipeline_stage: str, updated_before: datetime)` to `src/services/supabase/resources_dao.py` returning list of resource ids (or rows) where `pipeline_stage = $1` and `updated_at < $2`
- [x] T005 Add `mark_resource_failed(resource_id: str, failure_reason: str)` to `src/services/supabase/resources_dao.py` that sets `pipeline_stage = 'failed'` and `failure_reason = $2` for the given id
- [x] T006 Add `SCRAPE_STUCK_TIMEOUT_MINUTES` to Modal app-config env in `src/deployment/deploy.py` (push_modal_secrets); ensure `INGEST_STUCK_TIMEOUT_MINUTES` is included

**Checkpoint**: Foundation ready — US1, US2, US3 can proceed

---

## Phase 3: User Story 1 — End-to-End Pipeline Run (Priority: P1) — MVP

**Goal**: After a resource is scraped successfully, ingestion is started automatically so the full chain discovery → scrape → ingest runs without manual steps.

**Independent Test**: Run discovery; confirm new resources are created and scraped; confirm each scraped resource gets ingest spawned and moves to ingesting → complete or failed. Check Neo4j for completed resources.

- [x] T007 [US1] In `src/deployment/modal_workers.py`, after `await _scrape(resource_id)` returns successfully in `scrape_resource`, call `await ingest_resource.spawn.aio(resource_id)` so scrape completion spawns ingest for that resource

**Checkpoint**: Full pipeline discovery → scrape → ingest runs end-to-end

---

## Phase 4: User Story 2 — Resource-Pipeline Recovery (Priority: P2)

**Goal**: A scheduled process finds resources stuck in `scraping` or `ingesting` (older than configurable timeouts) and marks them failed with a clear reason.

**Independent Test**: Set a resource to `scraping` with old `updated_at`; run recovery; confirm it is marked `failed` with a stuck reason. Repeat for `ingesting`. Confirm recently updated resources are unchanged.

- [x] T008 [US2] Create `src/services/orchestration/__init__.py` and `src/services/orchestration/recovery.py` with `run_recovery_pipeline()` that loads settings, computes `updated_before` for `scraping` (now - scrape_stuck_timeout_minutes) and for `ingesting` (now - ingest_stuck_timeout_minutes), calls `list_stuck_resources` for each stage, then `mark_resource_failed(id, reason)` for each with reason "Stuck scraping timeout" or "Stuck ingesting timeout"; add structured logging for counts
- [x] T009 [US2] In `src/deployment/modal_workers.py`, add scheduled function `run_recovery_pipeline(schedule=modal.Period(minutes=15))` that imports and calls `run_recovery_pipeline()` from `src.services.orchestration.recovery`

**Checkpoint**: Stuck resources are marked failed on schedule; operators can inspect failure_reason

---

## Phase 5: User Story 3 — Manual Re-queue of Failed Resources (Priority: P3)

**Goal**: Operators can reset a failed resource to an early stage (discovered) so it re-enters the pipeline; re-queue is documented in runbook; optional API for operator UX.

**Independent Test**: Mark a resource failed; perform re-queue (SQL or API); confirm `pipeline_stage = discovered` and `failure_reason` null; trigger scrape (or discovery) and confirm it progresses again.

- [x] T010 [US3] Add `requeue_resource(resource_id: str)` to `src/services/supabase/resources_dao.py` that sets `pipeline_stage = 'discovered'` and `failure_reason = NULL` for the given id (leave `scraped_content` unchanged per data-model.md)
- [x] T011 [P] [US3] Add runbook section "Re-queue failed resource" in `docs/runbook.md` with SQL example (`UPDATE resources SET pipeline_stage = 'discovered', failure_reason = NULL WHERE id = '<uuid>'`) and how to re-trigger (e.g. `modal run src.deployment.modal_workers::scrape_resource --resource-id <uuid>`)
- [x] T012 [US3] Optional: Add `POST /api/v1/resources/{resource_id}/requeue` in `src/api/routes/resources/` that calls `requeue_resource` (or a thin service wrapper), returns 200 with updated resource or 404; protect with `get_current_user`; document in runbook as alternative to SQL

**Checkpoint**: Re-queue is available via runbook (and optionally API); operators can retry failed resources

---

## Phase 6: User Story 4 — Manual Triggers (Priority: P3)

**Goal**: Manual triggers for discovery (dry-run), scrape, and ingest are documented so operators and developers can debug and backfill without waiting for schedule.

**Independent Test**: Run discovery dry-run; run scrape for one resource id; run ingest for one resource id; confirm expected stage changes. All commands documented.

- [x] T013 [P] [US4] In `docs/runbook.md`, add or consolidate a short "Manual triggers" subsection that documents: discovery dry-run (`modal run ... run_discovery --dry-run`), discovery live, scrape one resource (`modal run ... scrape_resource --resource-id <uuid>`), ingest one resource (`modal run ... ingest_resource --resource-id <uuid>`); reference quickstart for full flow

**Checkpoint**: Manual triggers are documented; no code change (triggers already exist)

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: Recovery visibility, full-pipeline verification, and quickstart alignment.

- [x] T014 [P] Add runbook content for recovery: recovery schedule (e.g. every 15 min), how to run recovery manually (`modal run src.deployment.modal_workers::run_recovery_pipeline`), how to verify stuck→failed (Supabase query for resources by stage and updated_at)
- [x] T015 [P] Add or update runbook section for full-pipeline test: insert discovery source, run discovery, confirm resources flow discovered → scraping → scraped → ingesting → complete (or failed); reference `specs/001-pipeline-orchestration-recovery/quickstart.md` for step-by-step verification
- [x] T016 [P] Run quickstart.md validation: execute steps in `specs/001-pipeline-orchestration-recovery/quickstart.md` and confirm all checkpoints pass (or document any env/setup gaps)

---

## Optional: Tests (Recovery)

**Purpose**: Plan suggests unit tests for recovery; spec does not require tests. Include only if implementing tests.

- [x] T017 [P] [US2] Add unit test in `tests/unit/services/test_orchestration_recovery.py` (or equivalent) that mocks resources_dao and asserts `run_recovery_pipeline()` calls `list_stuck_resources` with correct stage and time bounds and calls `mark_resource_failed` for each returned id with the expected reason

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start first
- **Phase 2 (Foundational)**: Depends on Phase 1 (config cleanup before adding new timeout)
- **Phase 3 (US1)**: Depends on Phase 2 (no shared code; can start after T003–T006)
- **Phase 4 (US2)**: Depends on Phase 2 (T004, T005, T006)
- **Phase 5 (US3)**: Depends on Phase 2 (T010 uses same DAO; runbook and API can follow)
- **Phase 6 (US4)**: No code dependency — doc-only; can run in parallel with Phase 5 or 7
- **Phase 7 (Polish)**: Depends on Phase 4 and 5 (runbook sections reference recovery and re-queue)

### User Story Dependencies

- **US1 (P1)**: After Foundational — single file change in modal_workers
- **US2 (P2)**: After Foundational — orchestration service + Modal scheduled function
- **US3 (P3)**: After Foundational — DAO requeue + runbook + optional API
- **US4 (P3)**: Independent — documentation only

### Parallel Opportunities

- T001 and T002 can run in parallel (config vs deploy)
- T003, T004, T005 can run in parallel (different config/DAO methods)
- After Phase 2: T007 (US1), T008 (US2), T010 (US3) can be done in parallel by different owners
- T011 and T012 (US3 runbook vs optional API) can be parallel
- T013 (US4), T014, T015 (runbook sections) can be parallel
- T017 (optional test) is [P] with other US2 work

---

## Parallel Example: After Foundational

```text
# US1 owner
T007: In modal_workers.py add ingest spawn after scrape success

# US2 owner
T008: Create orchestration/recovery.py with run_recovery_pipeline()
T009: Add run_recovery_pipeline scheduled function in modal_workers.py

# US3 owner
T010: Add requeue_resource to resources_dao.py
T011: Add runbook section Re-queue failed resource
T012: (Optional) Add POST .../requeue endpoint
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Config cleanup (T001, T002)
2. Phase 2: Foundational (T003–T006)
3. Phase 3: US1 (T007) — wire scrape → ingest spawn
4. **Validate**: Run discovery, confirm resources flow to scraped then ingest spawns and resources reach complete/failed
5. Deploy/demo

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → full pipeline (discovery → scrape → ingest) → MVP
3. US2 → recovery (stuck → failed) → operators see clear failure reasons
4. US3 → re-queue (runbook + optional API) → operators can retry
5. US4 + Polish → docs and runbook complete

### Task Summary

| Phase        | Tasks   | Story |
|-------------|---------|--------|
| Phase 1 Setup | T001–T002 | — |
| Phase 2 Foundational | T003–T006 | — |
| Phase 3 US1 | T007 | US1 |
| Phase 4 US2 | T008–T009 | US2 |
| Phase 5 US3 | T010–T012 | US3 |
| Phase 6 US4 | T013 | US4 |
| Phase 7 Polish | T014–T016 | — |
| Optional Tests | T017 | US2 |

**Total**: 17 tasks (16 required, 1 optional test).  
**Per story**: US1: 1; US2: 2 (+1 optional test); US3: 3; US4: 1.  
**Suggested MVP scope**: Phase 1 + Phase 2 + Phase 3 (T001–T007).

---

## Notes

- [P] tasks use different files or have no ordering dependency.
- [Story] maps to spec.md user stories for traceability.
- Each user story is independently testable via runbook/quickstart.
- Commit after each task or logical group.
- Re-queue default: runbook (SQL + Modal) satisfies FR-005; API (T012) is optional for UX.
