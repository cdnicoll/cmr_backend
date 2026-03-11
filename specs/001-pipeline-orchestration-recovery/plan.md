# Implementation Plan: Phase 8 — Pipeline Orchestration and Recovery

**Branch**: `001-pipeline-orchestration-recovery` | **Date**: 2025-03-10 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/001-pipeline-orchestration-recovery/spec.md`

## Summary

Wire the full pipeline so discovery → scrape → ingest runs as a single spawn chain; add a scheduled resource-pipeline recovery function that marks resources stuck in `scraping` or `ingesting` (beyond configurable timeouts) as failed; add manual re-queue for failed resources and document (or add) manual triggers for each stage. No jobs table or `recover_orphaned_jobs` — recovery applies only to resource `pipeline_stage`. Stack: Python 3.11, existing FastAPI/Supabase/Modal; new scheduled recovery function; optional API for re-queue and manual triggers.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, Supabase (asyncpg/resources DAO), Modal (scheduled + spawn)  
**Storage**: PostgreSQL (Supabase) — existing `resources` table; no new tables  
**Testing**: pytest for recovery/orchestration logic where applicable; runbook-driven manual verification for full pipeline and recovery  
**Target Platform**: Modal (scheduled discovery already; add scheduled recovery); local/API for re-queue and manual triggers  
**Project Type**: Web service (API) + scheduled background workers  
**Performance Goals**: Recovery run completes in a few minutes for hundreds of resources; scrape→ingest spawn is fire-and-forget  
**Constraints**: Recovery and orchestration act only on resource pipeline state; no POST /jobs or jobs-table recovery  
**Scale/Scope**: Hundreds to low thousands of resources; configurable stuck timeouts per stage (scraping, ingesting)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Quick Start**: No new setup that blocks the 10-minute path; new env (e.g. `SCRAPE_STUCK_TIMEOUT_MINUTES`) documented in runbook and deploy secrets.
- **REST API**: Optional new endpoint(s) for re-queue (and optionally manual trigger) — or re-queue via runbook/CLI only; health and docs unchanged.
- **Cloud-Ready**: Recovery worker stateless; config from env/Settings; deploy via existing Modal deploy.
- **Observability**: Existing logging; log recovery run counts (marked failed per stage) and re-queue actions.
- **Developer Guidance**: Follow `_local/starter-kit/patterns.md`, `_local/starter-kit/modal-jobs.md` (scheduled function pattern; CMR uses resource-pipeline recovery only), `_local/starter-kit/stack-wiring.md`.

**Result**: Pass — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-pipeline-orchestration-recovery/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0: optional — timeout defaults, re-queue surface (API vs CLI)
├── data-model.md        # Phase 1: optional — recovery query shape, config fields (no new tables)
├── quickstart.md        # Phase 1: run full pipeline, run recovery, re-queue, verify
├── contracts/           # Phase 1: recovery run invocation; re-queue contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit.tasks — not created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── api/
│   └── routes/
│       └── resources/   # Optional: POST/PATCH re-queue, optional manual trigger endpoints
├── deployment/
│   └── modal_workers.py # 1) scrape_resource: after success, spawn ingest_resource
│                        # 2) run_recovery_pipeline(schedule=Period(minutes=15)): find stuck, mark failed
├── models/
│   └── config.py        # Add SCRAPE_STUCK_TIMEOUT_MINUTES (default e.g. 15); INGEST_STUCK_* exists
├── services/
│   ├── orchestration/   # NEW (or under resources): recovery + re-queue logic
│   │   ├── __init__.py
│   │   └── recovery.py # run_recovery_pipeline(): list stuck (scraping/ingesting), mark failed
│   └── supabase/
│       └── resources_dao.py # Add: list_stuck_resources(stages, updated_before_ts); requeue_resource(id)
docs/
├── runbook.md           # Add: recovery schedule, re-queue, full-pipeline verification
└── db/
    └── migrations/      # None (no schema change)
tests/
```

**Structure Decision**: Single backend. Orchestration: (1) Wire scrape → ingest in `modal_workers.scrape_resource` (after `_scrape` returns successfully, spawn `ingest_resource`). (2) New scheduled function `run_recovery_pipeline` in `modal_workers.py` calling a small recovery service that uses new DAO methods to list stuck resources and mark them failed. (3) Re-queue: new DAO method to set `pipeline_stage = discovered`, `failure_reason = null`; expose via API (e.g. `POST /api/v1/resources/{id}/requeue`) or runbook-only (e.g. SQL or CLI). Manual triggers for scrape/ingest already exist via `modal run ... --resource-id <id>`; discovery dry-run exists; document in quickstart/runbook.

## Complexity Tracking

No constitution violations; table left empty.

## Phase 0: Research

- **Scrape → ingest chain**: Implement in Modal worker: after `_scrape(resource_id)` returns without exception, call `ingest_resource.spawn.aio(resource_id)`. No HTTP; same app. Ingestion worker already idempotent (checks `pipeline_stage == scraped`).
- **Recovery timeouts**: Use `SCRAPE_STUCK_TIMEOUT_MINUTES` (new, default 15) for `scraping`; existing `INGEST_STUCK_TIMEOUT_MINUTES` (30) for `ingesting`. Single recovery function queries both stages with respective thresholds.
- **Re-queue surface**: Option A — runbook only (SQL or `modal run` a small script). Option B — `POST /api/v1/resources/{id}/requeue` that calls DAO and returns 200. Option B preferred for operator UX; no new route if product prefers CLI-only.
- **Manual triggers**: Discovery dry-run and live already via `modal run ... run_discovery`. Scrape and ingest via `modal run ... scrape_resource|ingest_resource --resource-id <id>`. No API change required; document in runbook and quickstart.

## Phase 1: Design

- **Data model**: No new tables. Recovery: query `resources` WHERE `pipeline_stage IN ('scraping','ingesting')` AND `updated_at < (now - timeout)`. Re-queue: UPDATE `pipeline_stage = 'discovered'`, `failure_reason = NULL` WHERE `id = ?`.
- **Contracts**: [contracts/](./contracts/) — recovery run (schedule, timeout config); re-queue (id, response).
- **Quickstart**: [quickstart.md](./quickstart.md) — run discovery → verify scrape → ingest chain; run recovery; re-queue a failed resource; verify.

## Post–Phase 1 Constitution Re-check

- Quick Start: New env optional; runbook additive. **Pass**
- REST API: Optional re-queue endpoint or runbook-only. **Pass**
- Cloud-Ready: Stateless recovery worker. **Pass**
- Observability: Logging in recovery and re-queue. **Pass**
- Developer Guidance: Runbook and patterns. **Pass**

**Result**: Pass.

## Phase 8 deliverables (implementation checklist)

These four items must be implemented; doc updates are part of the same phase.

| # | Deliverable | Spec ref | Notes |
|---|-------------|----------|--------|
| 1 | **Scrape → ingest spawn** | FR-002 / US1.2 | After successful scrape, spawn ingest for that resource (e.g. in `scrape_resource`: after `_scrape(resource_id)`, if resource is in `scraped`, call `ingest_resource.spawn(resource_id)`). |
| 2 | **Scheduled recovery** | FR-003 / US2 | New scheduled Modal function (e.g. every 15 min) that finds resources in `scraping` or `ingesting` with `updated_at` older than configurable timeouts and marks them `failed` with a clear reason. Uses DAO helpers + `SCRAPE_STUCK_TIMEOUT_MINUTES` and `INGEST_STUCK_TIMEOUT_MINUTES`; add timeouts to deploy app-config secret. |
| 3 | **Manual re-queue in runbook** | FR-005 / US3 | Runbook section "Re-queue failed resource" with SQL (e.g. `UPDATE resources SET pipeline_stage = 'discovered', failure_reason = NULL WHERE id = '<uuid>'`) and how to re-trigger (e.g. `modal run ...::scrape_resource --resource-id <uuid>` or ingest as appropriate). |
| 4 | **Scrape stuck timeout + config cleanup** | FR-010 | Add `SCRAPE_STUCK_TIMEOUT_MINUTES` to config and deploy; use it in recovery. **Remove or repurpose** `job_stuck_timeout_minutes` / `JOB_STUCK_TIMEOUT_MINUTES` from `src/models/config.py` and `src/deployment/deploy.py` — the job queue has been dropped. |

## Implementation Outline (for tasks.md)

0. **Config cleanup**: Remove `job_stuck_timeout_minutes` (and `JOB_STUCK_TIMEOUT_MINUTES` from deploy secrets) from the codebase; job queue is dropped.
1. **Config**: Add `scrape_stuck_timeout_minutes` to Settings and deploy secrets (`SCRAPE_STUCK_TIMEOUT_MINUTES`); ensure `INGEST_STUCK_TIMEOUT_MINUTES` is in deploy.
2. **DAO**: Add `list_stuck_resources(stages: list[str], updated_before: datetime)` (or equivalent per-stage timeouts) and optionally `requeue_resource(resource_id: str)` to resources_dao; recovery uses these to find and mark stuck resources failed.
3. **Recovery service**: New `orchestration.recovery` (or under resources) — `run_recovery_pipeline()`: for `scraping` and `ingesting`, query stuck using timeouts, then mark each failed with reason (e.g. "Stuck scraping timeout" / "Stuck ingesting timeout").
4. **Modal**: In `scrape_resource`, after successful `_scrape(resource_id)`, spawn ingest when resource is in `scraped` (e.g. re-fetch resource and if `pipeline_stage == 'scraped'` call `ingest_resource.spawn(resource_id)`). Add scheduled function (e.g. `recover_stuck_resources`, `Period(minutes=15)`), calling recovery service.
5. **Re-queue**: Implement requeue in service/DAO if desired; re-queue is **documented in runbook** (SQL + Modal commands) as the supported operator path (FR-005).
6. **Runbook**: Add section "Re-queue failed resource" with SQL and Modal re-trigger commands; document recovery schedule, how to verify stuck→failed, and full-pipeline test.
7. **Tests**: Unit tests for recovery (stuck listing, mark failed); optional integration test for requeue.
