# Starter Kit — Modal Jobs

How Modal is configured, how jobs are defined and run, and how to add new jobs.

---

## Modal Configuration

### API App

**File**: `src/deployment/modal_app.py`

- **App name**: `API-{ENVIRONMENT}` (e.g. `API-develop`)
- **Image**: Debian slim, Python 3.11, pip-installed deps, `add_local_dir("src")`
- **Secrets**: `supabase-credentials-{ENV}`, `app-config-{ENV}`, `apollo-credentials-{ENV}`, `llm-credentials-{ENV}`
- **Function**: `@asgi_app()` wraps FastAPI app
- **Resources**: 1 CPU, 512MB, 300s timeout, max 100 containers, region `ca`

### Worker App

**File**: `src/deployment/modal_workers.py`

- **App name**: `Job-Worker-{ENVIRONMENT}`
- **Images**: `base_image`, `browser_image`, `gpu_image` (layered)
- **Secrets**: Same pattern as API app

---

## Job Definition Pattern

Each worker is an `@app.function()` with:

- `image` — base, browser, or gpu
- `secrets` — env-specific
- `timeout`, `cpu`, `memory`, `max_containers`
- `region="ca"`
- Signature: `(job_id: str, job_type: str, user_id: str, job_parameters: dict)`

Shared logic lives in `_process_job()`, which:

1. Sets up Python path
2. Loads settings and logging
3. Gets Supabase client (service role)
4. Calls `JobQueueService.process_job()`
5. Optionally deletes PGMQ message on success
6. Re-raises on error

### Tier Mapping

| Tier | Function | Job Types (examples) | Resources |
|------|----------|----------------------|-----------|
| GPU | `process_gpu_job` | document_index (PDF vectorization) | T4, 8GB, 15min |
| Browser | `process_browser_job` | web_crawl | 2 CPU, 2GB, 5min |
| LLM | `process_llm_job` | document_process, llm_task | 1 CPU, 1GB, 5min |
| API | `process_api_job` | company_enrich | 0.5 CPU, 512MB, 2min |

---

## Job Lifecycle

```
1. Client POST /jobs (JobCreateRequest)
2. JobQueueService.create_job():
   - validate_job_parameters()
   - check_duplicate_job()
   - database.create_job() → jobs table (status=pending)
   - queue.send_job_message() → PGMQ
   - spawner.spawn_job() → Modal Function.spawn()
3. Modal worker runs _process_job():
   - database.update_job_status(processing)
   - JobQueueService.process_job() → domain logic
   - database.store_data_references() on success
   - database.update_job_status(completed) or store_error_info + failed
4. Recovery worker (every 15 min):
   - find_stuck_jobs() → processing + updated_at > timeout
   - recover_stuck_job() → mark failed
   - orphaned pending → mark_job_failed()
```

---

## API Endpoint That Kicks Off Jobs

**Route**: `POST /jobs`  
**File**: `src/api/routes/jobs/router.py`

**Payload**: `JobCreateRequest` with `job_type` and `job_parameters`.

**Flow**:

1. `get_current_user` validates JWT
2. `JobQueueService.create_job()`:
   - Validates parameters per job type
   - Checks for duplicate (same entity, pending/processing)
   - Inserts into `jobs` table
   - Sends to PGMQ
   - Calls `spawn_job()` to invoke Modal

**Validation**: Per-job-type in `JobQueueService.validate_job_parameters()` (company/document/relationship existence, etc.).

---

## Orphaned Jobs and Recovery

**Route**: None — recovery is a **scheduled Modal function**, not an API endpoint.

**Function**: `recover_orphaned_jobs()` in `src/deployment/modal_workers.py`

**Schedule**: `Period(minutes=15)`

### What Counts as Orphaned

1. **Stuck processing**: `status='processing'` and `updated_at < NOW() - timeout_minutes`
2. **Orphaned pending**: `status='pending'`, `created_at < NOW() - timeout_minutes`, `retry_count < 2`

### Actions

- **Stuck processing**: `recover_stuck_job()` → `mark_job_failed(..., "Job exceeded maximum processing time", "JobTimeoutError")`
- **Orphaned pending**: `mark_job_failed(..., "Job never started (pending timeout)", "PendingTimeoutError")`

**Config**: `JOB_STUCK_TIMEOUT_MINUTES` (default 15).

---

## Job State Storage

**Table**: `public.jobs`

| Column | Purpose |
|--------|---------|
| id | UUID (PK) |
| job_type | document_index, web_crawl, company_enrich, etc. |
| status | pending, processing, completed, failed |
| user_id | Creator |
| job_parameters | JSONB |
| error_message, error_type, error_context | Failure details |
| data_references | JSONB (outputs) |
| retry_count | For recovery logic |
| created_at, updated_at, started_at, completed_at | Timestamps |

**PGMQ**: Backup queue; messages contain `job_id`, `job_type`, `user_id`, `job_parameters`. Deleted on successful processing.

---

## Retry and Error Handling

- **No automatic retries** for failed jobs.
- On failure: `store_error_info()`, `update_job_status(failed)`.
- Recovery worker only marks stuck/orphaned jobs as failed; it does not re-spawn.
- `retry_count` is used in recovery to avoid re-processing (e.g. `retry_count < 2` for pending).

---

## Adding a New Modal Job

1. **Add job type** to `JobType` in `src/models/jobs/job_status.py`.

2. **Map to tier** in `src/services/job_queue/spawner.py`:
   ```python
   JOB_TIER_MAPPING[JobType.NEW_TYPE.value] = "process_llm_job"  # or gpu/browser/api
   ```

3. **Validate parameters** in `JobQueueService.validate_job_parameters()`.

4. **Extract entity** in `JobQueueService.extract_entity_reference()` for duplicate check.

5. **Implement processing** in `JobQueueService.process_job()`:
   ```python
   elif job_type == JobType.NEW_TYPE.value:
       # Domain logic
       await database.store_data_references(job_id, {...})
       await self.update_job_status(job_id, JobStatus.COMPLETED, ...)
   ```

6. **Duplicate check** in `database.check_duplicate_job()` if entity key differs.

7. **Deploy** workers: `uv run deploy_dev` or `deploy_prod`.
