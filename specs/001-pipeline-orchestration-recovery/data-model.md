# Phase 1: Data Model — Pipeline Orchestration and Recovery

No new tables. This feature only uses existing `resources` columns and new config.

## Recovery query

- **Stuck resources**: `resources` WHERE `pipeline_stage IN ('scraping', 'ingesting')` AND `updated_at < $updated_before`.
  - `updated_before` is computed per stage: `now - SCRAPE_STUCK_TIMEOUT_MINUTES` for `scraping`, `now - INGEST_STUCK_TIMEOUT_MINUTES` for `ingesting`.
- **Update**: Set `pipeline_stage = 'failed'`, `failure_reason = 'Stuck scraping timeout'` or `'Stuck ingesting timeout'` (or equivalent) for each stuck row.

## Re-queue

- **Update**: For a given `resource_id`, set `pipeline_stage = 'discovered'`, `failure_reason = NULL`. Optional: clear `scraped_content` if product wants a full re-scrape; spec says "reset to an early stage" — leaving `scraped_content` allows re-running only ingest if desired; clearing it forces full re-scrape. Default: leave `scraped_content` unchanged so re-queue means "retry from discovery stage" (re-scrape and re-ingest).

## Config (Settings / env)

| Name | Purpose | Default |
|------|---------|---------|
| `SCRAPE_STUCK_TIMEOUT_MINUTES` | Max age for `scraping` before considered stuck; used by recovery | 15 |
| `INGEST_STUCK_TIMEOUT_MINUTES` | Max age for `ingesting` before considered stuck; used by recovery | 30 (existing) |

**Phase 8 cleanup:** Remove `JOB_STUCK_TIMEOUT_MINUTES` / `job_stuck_timeout_minutes` from Settings and from deploy app-config secret. The job queue has been dropped; recovery applies only to resource `pipeline_stage`, using the two timeouts above.
