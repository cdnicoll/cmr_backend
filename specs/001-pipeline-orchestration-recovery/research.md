# Phase 0: Research — Pipeline Orchestration and Recovery

Resolved choices for Phase 8 implementation.

## Scrape → Ingest chain

- **Where to spawn ingest**: In the Modal `scrape_resource` function, after `_scrape(resource_id)` returns successfully (no exception). Call `ingest_resource.spawn.aio(resource_id)` so the same run completes scrape and enqueues ingest.
- **Why not in scraping service**: The scraping service has no reference to Modal; keeping spawn in the worker keeps the service layer free of deployment concerns.
- **Idempotency**: Ingestion worker already requires `pipeline_stage == scraped`; by the time spawn runs, the scrape flow has committed `scraped`, so ingest will run once per resource.

## Recovery timeouts

- **Scraping**: New config `SCRAPE_STUCK_TIMEOUT_MINUTES` (default 15). Resources in `scraping` with `updated_at` older than this are considered stuck.
- **Ingesting**: Existing `INGEST_STUCK_TIMEOUT_MINUTES` (default 30). Same rule for `ingesting`.
- **Single recovery function**: One scheduled function runs periodically; it queries stuck resources for both stages (each with its own threshold), then marks each as failed with a distinct reason (e.g. "Stuck scraping timeout", "Stuck ingesting timeout").

## Re-queue surface

- **Behavior**: Set `pipeline_stage = 'discovered'`, `failure_reason = NULL` for the given resource so it re-enters the pipeline.
- **Options**: (A) Runbook-only (SQL or one-off script). (B) API endpoint e.g. `POST /api/v1/resources/{id}/requeue`. Recommendation: (B) for operator UX; implement in Phase 1/tasks.

## Manual triggers

- **Discovery**: Already available — `modal run ... run_discovery` with `--dry-run` or without.
- **Scrape / Ingest**: Already available — `modal run ... scrape_resource --resource-id <id>` and `modal run ... ingest_resource --resource-id <id>`. No new surface; document in runbook and quickstart.
