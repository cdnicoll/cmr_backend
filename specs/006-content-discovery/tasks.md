# Tasks: Content Discovery (Sitemap, RSS, YouTube)

**Input**: Design documents from `specs/006-content-discovery/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not requested in spec; runbook-driven manual verification per plan. No test tasks included.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `docs/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, discovery package structure, and dependencies for discovery workers.

- [X] T001 Create discovery domain package: `src/services/discovery/__init__.py`, and placeholder modules for `service`, `sitemap_scanner`, `rss_scanner`, `youtube_scanner` in `src/services/discovery/`
- [X] T002 [P] Add discovery worker dependencies to Modal image in `src/deployment/modal_workers.py`: `feedparser` (RSS) and YouTube Data API client (e.g. `google-api-python-client` or httpx-based) so `run_discovery` can run sitemap/RSS/YouTube scanners
- [X] T003 [P] Add optional discovery config defaults in `src/models/config.py`: e.g. `DISCOVERY_DAYS_BACK_DEFAULT`, `DISCOVERY_BATCH_SIZE` (per research.md and plan)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data layer and resource creation extensions that ALL user stories depend on. No user story work can begin until this phase is complete.

- [X] T004 Document migration application in `docs/runbook.md`: add step to apply `docs/db/migrations/004_discovery_sources.sql` (or via existing `scripts/migrate.py` if migration runner includes it)
- [X] T005 [P] Implement discovery_sources DAO in `src/services/supabase/discovery_sources_dao.py`: `list_enabled_sources()` returning enabled rows, `get_by_id(id)` for single source; use asyncpg and `load_settings().transaction_pooler_url` per existing DAO pattern
- [X] T006 Extend `insert_resource` in `src/services/supabase/resources_dao.py`: add optional parameter `discovery_source_id: str | None = None`; include it in INSERT and RETURNING
- [X] T007 Add `get_existing_urls(urls: list[str]) -> set[str]` in `src/services/supabase/resources_dao.py`: single query returning set of URLs that already exist in `resources` for deduplication
- [X] T008 Extend `batch_create` in `src/services/resources_service.py`: add optional parameter `discovery_source_id: str | None = None`; pass it through to each `insert_resource` call for created resources

**Checkpoint**: Foundation ready — discovery_sources table (migration), DAO for sources, resources DAO/service support for discovery_source_id and bulk URL lookup. User story implementation can begin.

---

## Phase 3: User Story 1 — Daily automated discovery (Priority: P1) — MVP

**Goal**: Scheduled discovery reads all enabled sources (sitemap, RSS, YouTube), collects candidate URLs, filters and deduplicates, creates net-new resources with "discovered" status, and triggers scraping only for those created in the run.

**Independent Test**: Run discovery once with at least one source of each type configured; verify new resources appear with "discovered" status and duplicate URLs are not created when run again. Confirm scrape is triggered only for net-new resources.

### Implementation for User Story 1

- [X] T009 [P] [US1] Implement sitemap scanner in `src/services/discovery/sitemap_scanner.py`: fetch sitemap URL via httpx, parse with `xml.etree.ElementTree` (urlset and sitemapindex with capped recursion), apply config filters (days_back, require_https, required_path_patterns, excluded_path_patterns, max_path_depth) per data-model.md and research.md
- [X] T010 [P] [US1] Implement RSS scanner in `src/services/discovery/rss_scanner.py`: fetch feed via httpx, parse with feedparser, apply config filters (days_back, min_relevance_score, require_https) per data-model.md
- [X] T011 [P] [US1] Implement YouTube scanner in `src/services/discovery/youtube_scanner.py`: use YouTube Data API v3 (channelId / uploads playlist or search.list), form video URLs; config from source `config` (channel_id, max_videos); require YOUTUBE_API_KEY from env/Modal secret
- [X] T012 [US1] Implement discovery service in `src/services/discovery/service.py`: `run_discovery(dry_run: bool = False)`: load enabled sources via discovery_sources_dao; for each source run appropriate scanner in try/except (per-source failure does not abort run; log and continue), keeping URLs grouped by source (e.g. list of (source_id, urls) or dict source_id → urls); call `get_existing_urls` once over all candidate URLs to get existing set; for each source, filter that source's URLs to net-new (not in existing set), then call `batch_create(net_new_urls, discovery_source_id=source_id)` so provenance is set; collect created resource IDs from each batch_create response (results where status == "created"); return created IDs for scrape spawn (see T013); use `get_logger(__name__)` and structured logging
- [X] T013 [US1] Add `run_discovery` Modal function in `src/deployment/modal_workers.py`: `@app.function` with image that includes discovery deps, timeout e.g. 600s, `schedule=modal.Period(days=1)`, secrets; invoke discovery service; for each resource ID returned as created, call `scrape_resource.spawn(resource_id)` (when not dry_run); support optional `dry_run` parameter for manual/CLI runs
- [X] T014 [US1] Wire discovery service to resources and scrape: ensure `src/services/discovery/service.py` calls `batch_create` from `src/services.resources_service` and that Modal `run_discovery` obtains created IDs from service return value and calls `scrape_resource.spawn` for each (in-process, no HTTP to API)

**Checkpoint**: User Story 1 complete. Run discovery with one sitemap, one RSS, one YouTube source; confirm resources created with pipeline_stage=discovered, no duplicates on re-run, scrape spawned only for new resources.

---

## Phase 4: User Story 2 — Operators configure and manage discovery sources (Priority: P2)

**Goal**: Operators can add, update, and manage sources (sitemap, RSS, YouTube) without redeploying; sources have type, config, and enabled flag. Discovery respects enabled flag and per-source config.

**Independent Test**: Add one source of each type (sitemap, RSS, YouTube) and run discovery; confirm each source is read and produces the expected kind of URLs. Disable a source and confirm it is skipped.

### Implementation for User Story 2

- [X] T015 [P] [US2] Document adding/updating discovery sources in `docs/runbook.md`: add section for discovery_sources table, how to insert/update rows (SQL examples from quickstart.md), enable/disable, and how to verify discovery uses them
- [X] T016 [US2] Ensure discovery service in `src/services/discovery/service.py` skips sources with `enabled = false` (list_enabled_sources already enforces this) and applies per-source config (config.url, config.feed_url, config.channel_id, days_back, etc.) from each source row; add or reuse validation for source_type and config shape per data-model.md when loading sources

**Checkpoint**: User Story 2 complete. Add/disable sources via DB; run discovery and verify behavior per source config.

---

## Phase 5: User Story 3 — Safe testing with dry-run (Priority: P3)

**Goal**: Operators can run discovery in dry-run mode: all reading and filtering, no resource creation, no scrape triggers; system reports what would have been submitted (counts per source, sample URLs).

**Independent Test**: Run discovery in dry-run with one or more sources; confirm no new resources and no scrape jobs, and logs/output show what would have been submitted.

### Implementation for User Story 3

- [X] T017 [US3] Add dry_run behavior in `src/services/discovery/service.py`: when `dry_run=True`, run all scanners and filters and dedupe, but do not call `batch_create` and do not return created IDs for scrape; log or return summary (counts per source, total URLs that would be submitted, optional sample URLs)
- [X] T018 [US3] Support dry-run invocation for Modal `run_discovery` in `src/deployment/modal_workers.py`: accept `dry_run` (e.g. CLI `modal run ... --dry-run` or function arg); pass to discovery service; ensure no `scrape_resource.spawn` calls when dry_run is True; log "DRY RUN: no resources created, no scrape spawned" and summary per contracts/discovery-run-invocation.md

**Checkpoint**: User Story 3 complete. Run `modal run src.deployment.modal_workers::run_discovery --dry-run` and verify no side effects and clear reporting.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Runbook, quickstart validation, and cross-cutting clarity.

- [X] T019 [P] Add discovery section to `docs/runbook.md`: run discovery (dry-run then live), verify resources and scrape, idempotency check; reference quickstart.md and YOUTUBE_API_KEY; troubleshooting (no sources run, YouTube errors, per-source failures)
- [X] T020 Validate quickstart flow: apply migration, add at least one source, run discovery dry-run, run discovery for real, re-run and confirm no duplicate resources; update quickstart.md or runbook if steps diverge

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately.
- **Phase 2 (Foundational)**: Depends on Setup — BLOCKS all user stories.
- **Phase 3 (US1)**: Depends on Foundational — MVP.
- **Phase 4 (US2)**: Depends on Foundational; overlaps with US1 (discovery already uses sources). Can follow US1 or run in parallel if US1 is done.
- **Phase 5 (US3)**: Depends on US1 (run_discovery exists); add dry_run without breaking live runs.
- **Phase 6 (Polish)**: Depends on US1–US3 for accurate runbook and quickstart.

### User Story Dependencies

- **US1 (P1)**: After Phase 2. No dependency on US2/US3.
- **US2 (P2)**: After Phase 2. Discovery service (US1) must use per-source config; runbook (US2) documents how to configure.
- **US3 (P3)**: After US1 (run_discovery and service exist). Dry-run is an additive parameter.

### Within Each User Story

- Scanners (T009–T011) can be implemented in parallel.
- Discovery service (T012) depends on scanners and DAOs.
- Modal run_discovery (T013–T014) depends on discovery service.

### Parallel Opportunities

- Phase 1: T002 and T003 [P] in parallel after T001.
- Phase 2: T005 [P] in parallel with T006/T007/T008 after T004.
- Phase 3: T009, T010, T011 [P] in parallel; then T012 → T013 → T014 sequential.
- Phase 4: T015 [P] with T016.
- Phase 6: T019 [P] with T020.

---

## Parallel Example: User Story 1

```text
# Scanners in parallel (different files):
T009: sitemap_scanner in src/services/discovery/sitemap_scanner.py
T010: rss_scanner in src/services/discovery/rss_scanner.py
T011: youtube_scanner in src/services/discovery/youtube_scanner.py

# Then sequential:
T012: discovery service (uses all three scanners)
T013: Modal run_discovery (calls service, spawns scrape)
T014: wire service to batch_create and scrape (confirm in T012/T013)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup  
2. Complete Phase 2: Foundational  
3. Complete Phase 3: User Story 1  
4. **STOP and VALIDATE**: Run discovery with one source per type; verify resources and no duplicates; confirm scrape spawned for new resources only.  
5. Deploy/demo if ready.

### Incremental Delivery

1. Setup + Foundational → foundation ready.  
2. Add US1 → test independently → deploy (MVP).  
3. Add US2 → runbook and per-source config → test.  
4. Add US3 → dry-run → test.  
5. Polish → runbook and quickstart validation.

### Suggested MVP Scope

- **MVP**: Phase 1 + Phase 2 + Phase 3 (User Story 1).  
- Delivers: scheduled discovery, all three source types, dedupe, net-new create, scrape for created only.  
- US2 and US3 add operator-friendly configuration and safe dry-run without changing core behavior.

---

## Notes

- Migration file `docs/db/migrations/004_discovery_sources.sql` already exists; Phase 2 focuses on runbook and DAO/service code.
- No new REST endpoints; discovery runs as Modal scheduled/manual function.
- Per-source failure: catch exceptions per source, log, continue; do not abort entire run (FR-011).
- Format: every task uses `- [ ] [TaskID] [P?] [Story?] Description with file path`.
