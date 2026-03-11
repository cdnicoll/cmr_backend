# Phase 8 implementation review vs build plan

**Date**: 2025-03-08  
**Build plan**: `_local/build-plan.md` — Phase 8: Pipeline Orchestration and Recovery

## Verdict: **Aligns with build plan** ✓

The implementation satisfies all four build-plan bullets and the documented test criteria. Two small config/doc cleanups are recommended below.

---

## Build plan vs implementation

| Build plan requirement | Implementation | Status |
|------------------------|----------------|--------|
| **Unified pipeline: discovery → scrape → ingest (scrape spawns ingest on success)** | `modal_workers.scrape_resource`: after `await _scrape(resource_id)` calls `await ingest_resource.spawn.aio(resource_id)`. Discovery already spawns scrape for created IDs. | ✓ |
| **Scheduled recovery** (e.g. every 15 min; stuck `scraping`/`ingesting` → `failed`; no jobs table) | `run_recovery_pipeline()` in `modal_workers.py` with `schedule=modal.Period(minutes=15)`; `orchestration.recovery.run_recovery_pipeline()` uses `list_stuck_resources` + `mark_resource_failed`; config uses `SCRAPE_STUCK_TIMEOUT_MINUTES` and `INGEST_STUCK_TIMEOUT_MINUTES`. | ✓ |
| **Manual re-queue** (runbook SQL + Modal re-trigger; optional API) | Runbook section "Re-queue failed resource" with SQL and `modal run ... scrape_resource --resource-id <uuid>`; `POST /api/v1/resources/<id>/requeue` in `router.py`; `requeue_resource()` in `resources_dao.py`. | ✓ |
| **Manual triggers** (discovery dry-run, scrape one, ingest one) documented | Runbook "Manual triggers" table with all four commands; quickstart referenced. | ✓ |

---

## Test criteria (build plan)

- **Full pipeline end-to-end** — Runbook "Full-pipeline test" + quickstart; scrape→ingest spawn in code. ✓
- **Stuck scraping → failed** — Recovery uses `list_stuck_resources("scraping", scrape_cutoff)` and `mark_resource_failed(..., "Stuck scraping timeout")`. ✓
- **Stuck ingesting → failed** — Same for `ingesting` and `"Stuck ingesting timeout"`. ✓
- **Re-queue failed → discovered** — DAO `requeue_resource`; runbook SQL and API. ✓
- **Modal dashboard (discovery + recovery)** — Both `run_discovery` and `run_recovery_pipeline` are Modal functions with schedules. ✓

---

## Config and deploy

- **config.py**: `job_stuck_timeout_minutes` removed; `scrape_stuck_timeout_minutes` (default 15) and `ingest_stuck_timeout_minutes` (default 30) present. ✓
- **deploy.py**: `SCRAPE_STUCK_TIMEOUT_MINUTES` and `INGEST_STUCK_TIMEOUT_MINUTES` in app-config; no `JOB_STUCK_TIMEOUT_MINUTES`. ✓

---

## Optional notes (no change required)

1. **Scrape → ingest spawn**: Ingress spawns after every `_scrape()` return (no check that `pipeline_stage == 'scraped'`). The ingest worker is idempotent: it skips with a log when stage ≠ scraped. So behavior is correct; optionally spawn only when stage is scraped to avoid a no-op ingest run.
2. **Re-queue API**: Returns 404 when `requeue_resource` updates 0 rows (invalid id). When 1 row updated, returns the resource from `get_resource_by_id`. Correct.

---

## Recommended cleanups

1. **`.env.example`** — Still has `JOB_STUCK_TIMEOUT_MINUTES=15` and no `SCRAPE_STUCK_TIMEOUT_MINUTES`. Should replace with `SCRAPE_STUCK_TIMEOUT_MINUTES=15` so env and runbook match the code.
2. **`scripts/create_modal_secrets.sh`** — Still references `JOB_STUCK_TIMEOUT_MINUTES` in the example command. Should reference `SCRAPE_STUCK_TIMEOUT_MINUTES` (or remove the line) for consistency.

Starter-kit and other spec docs that mention the old job queue are historical; no change needed there.
