# CMR Pain Points

This document captures areas of the codebase that appear overly complex, inconsistent, or hard to follow — useful for informing a rewrite.

---

## Complexity and Inconsistency

### 1. **Dual status tracking (insight_status vs graphiti_status)**

Two parallel status columns on `resource` with nearly identical semantics (pending/processing/completed/failed). Each has its own reset logic with different timeouts (60 min vs 120 min). A unified state machine or single "pipeline_status" might simplify reasoning.

### 2. **Cron job orchestration is implicit**

The pipeline (discovery → scrape → status → insight → ingest) is not explicitly modeled. Cron jobs call APIs in sequence, but there's no workflow engine or DAG. Ordering and timing are implicit in cron schedules. If one step is delayed, the next may run with nothing to do.

### 3. **2-second wait in resource_status_insight**

The "brief pause to allow immediate status updates" is arbitrary. Comment acknowledges "next cron run will catch delayed completions" — so the wait may add little value. Unclear if it was a workaround for a specific race.

### 4. **Job resurrection semantics**

`max_resurrection_attempts` for timed-out Apify jobs is configurable, but the interaction with `resurrection_attempts` on the jobs table and how resurrection actually works (re-run? new job?) is not fully documented in the domain docs. Code suggests resurrection is handled in JobStatusService.

### 5. **Content API path inconsistency**

Content generation lives at `/api/v1/trend-analysis/content` while trends is at `/api/v1/trends`. The "trend-analysis" prefix groups content under trends conceptually, but the routing is non-obvious.

### 6. **Celery + asyncio mixing**

Celery tasks are synchronous but call `asyncio.run()` to execute async service methods. This works but is a common source of "event loop already running" issues in tests or nested contexts. A dedicated async task runner (e.g. arq, dramatiq with async) could simplify.

### 7. **Insight agent retry logic**

JSON parsing retries (max 2) are embedded in the agent's `run_agent` with complex exception detection (`"json_invalid" in str(e)`). Fragile and tightly coupled to PydanticAI's error format.

### 8. **Graphiti episode size**

Target "<400 chars" for episode content is documented but not enforced in validation. Oversized content could cause Graphiti LLM failures that are hard to debug.

---

## Workarounds and Tech Debt

### 9. **Pending record before Celery queue (content generation)**

Content generation creates a DB record *before* queueing the task to avoid a race where the status endpoint is polled before Celery has the task. This is a valid fix but indicates the async flow (queue → poll) doesn't naturally support "task exists" semantics.

### 10. **cleanup_completed_*_tasks are placeholders**

`cleanup_completed_insight_tasks` and `cleanup_completed_graphiti_tasks` return `tasks_cleaned: 0` — no actual cleanup. Comment: "placeholder for cleanup logic." Task result storage (Redis) may grow unbounded.

### 11. **RSS discovery "not yet implemented"**

Sitemap scanner supports RSS sources but requires explicit `known_rss_feeds`. Discovery from a site's RSS auto-discovery links is not implemented.

### 12. **Rate limiting may not be key-scoped**

SlowAPI uses `get_remote_address` for rate limiting. API keys have `rate_limit_per_minute` and `rate_limit_per_hour`, but it's unclear if these are applied per-key or if all requests share a single limit.

### 13. **Persona webhook fallback**

PersonaService catches errors and returns a default persona. Failures are logged but not surfaced to the client. Silent degradation may hide integration issues.

### 14. **Database schema evolution**

Migrations are ad-hoc SQL files (e.g. `add_insight_status_column.sql`). No Alembic or migration runner — manual application. Schema in `db/setup.sql` may drift from migrations.

---

## Unclear Intent

### 15. **"Alignment" score in insights**

Insight model has `alignment: ScoreWithRationale | None` with comment "populated by secondary LLM." System prompt says "Do NOT generate alignment scores." The secondary process is not present in the codebase. Intent unclear.

### 16. **source_publication_date vs created_at**

Migration `remove_source_publication_date` suggests `source_publication_date` was removed. Eligibility queries use `created_at` for "publication window." Whether "publication" means "when we discovered it" or "when it was originally published" is ambiguous for some flows.

### 17. **Tasks API scope**

`/api/v1/tasks` has hello_world, status, list, cancel. These are generic Celery task operations. No direct integration with insight/graphiti/content task IDs returned by resource endpoints. Users must track task IDs from different domains separately.

### 18. **Health check degradation logic**

App is "degraded" if Neo4j is down but Postgres is up. However, some flows (e.g. resource creation) don't need Neo4j. The health model doesn't distinguish "core" vs "optional" dependencies.

---

## Summary

Key themes for a rewrite:

- **Unify pipeline state** — Single coherent model for resource lifecycle
- **Explicit workflow** — Replace implicit cron ordering with a defined pipeline/DAG
- **Async-native tasks** — Reduce asyncio.run() in sync Celery tasks
- **Clean up placeholders** — Implement or remove cleanup tasks; clarify persona/alignment
- **Schema and migrations** — Formalize migration strategy
- **Document resurrection and rate limits** — Ensure behavior matches intent
