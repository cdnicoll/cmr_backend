# Starter Kit — First-Run Expectations

This document defines what the starter should include when it is first run. Use it as a checklist when building or validating a new project from this blueprint.

---

## Overview

When you run the starter for the first time, you should have:

1. A **health check** endpoint
2. A **single sample worker** as the pattern for all future workers
3. **API endpoints** to trigger that worker
4. An **endpoint to clean up stuck or stale jobs**
5. A **database migration script** that sets up the bare minimum schema

---

## 1. Health Check

**Expectation**: At least one health endpoint that confirms the API and its dependencies are running.

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | API liveness — returns 200 when the app is up |
| `GET /health/db` | Database connectivity — returns 200 when Supabase and/or transaction pooler are reachable |

**Example response**:
```json
{"status": "ok"}
```

---

## 2. Sample Worker (Pattern for All Workers)

**Expectation**: A single Modal worker function that serves as the reference implementation for adding new workers.

- **Location**: `src/deployment/modal_workers.py`
- **Function**: e.g. `process_sample_job` — minimal logic that demonstrates the full lifecycle
- **Job type**: e.g. `sample_task` in `JobType` enum
- **Behavior**: Accepts `job_id`, `job_type`, `user_id`, `job_parameters`; updates job status; completes or fails with error info

**Why one sample**: New workers can be added by copying this pattern — same signature, same `_process_job` flow, same status updates.

---

## 3. API Endpoints to Hit Workers

**Expectation**: Endpoints that allow clients to create and monitor jobs.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /jobs` | POST | Create a job — validates params, inserts into DB, spawns worker, returns job ID and status |
| `GET /jobs/{job_id}` | GET | Get job status by ID |
| `GET /jobs` | GET | List jobs (with optional filters: status, type, pagination) |

**Payload for `POST /jobs`**:
```json
{
  "job_type": "sample_task",
  "job_parameters": {}
}
```

**Response**: Job object with `id`, `status`, `created_at`, etc.

---

## 4. Endpoint to Clean Up Stuck or Stale Jobs

**Expectation**: An endpoint that marks stuck or stale jobs as failed, similar to the scheduled recovery worker.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /jobs/recover` or `POST /admin/jobs/recover` | POST | Run orphan/stuck job recovery on demand |

**Behavior** (mirrors scheduled `recover_orphaned_jobs`):

1. **Stuck processing**: Jobs with `status='processing'` and `updated_at` older than timeout → mark as failed
2. **Orphaned pending**: Jobs with `status='pending'` and `created_at` older than timeout → mark as failed

**Config**: `JOB_STUCK_TIMEOUT_MINUTES` (e.g. 15)

**Response**: Summary of how many jobs were recovered (e.g. `{"recovered": 3, "stuck": 2, "orphaned": 1}`)

**Note**: The scheduled Modal recovery worker can still run in the background; this endpoint allows manual or scripted cleanup.

---

## 5. Database Migration Script

**Expectation**: A migration script that creates the bare minimum schema for the starter.

**Minimum schema**:

- **`jobs` table**: `id`, `job_type`, `status`, `user_id`, `job_parameters`, `error_message`, `error_type`, `error_context`, `data_references`, `retry_count`, `created_at`, `updated_at`, `started_at`, `completed_at`
- **PGMQ queue**: `job_queue` (or configurable name) — for job backup and recovery
- **`profiles` table** (if using auth): `id`, `company_id` — for JWT profile lookup

**Location**: e.g. `scripts/migrate.py` or `docs/db/migrations/001_initial.sql`

**Usage**:
```bash
uv run python scripts/migrate.py
# or
psql $DATABASE_URL -f docs/db/migrations/001_initial.sql
```

**Idempotency**: Script should be safe to run multiple times (e.g. `CREATE TABLE IF NOT EXISTS`, `CREATE EXTENSION IF NOT EXISTS` for PGMQ).

---

## Summary Checklist

| Item | Delivered |
|------|-----------|
| Health check (`/health`, `/health/db`) | ☐ |
| Single sample worker (`process_sample_job` / `sample_task`) | ☐ |
| API: `POST /jobs`, `GET /jobs`, `GET /jobs/{id}` | ☐ |
| API: `POST /jobs/recover` (or equivalent) for stuck/stale cleanup | ☐ |
| Database migration script (jobs table, PGMQ, profiles if needed) | ☐ |
