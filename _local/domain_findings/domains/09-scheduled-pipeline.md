# Domain: Scheduled Pipeline (Cron)

## Purpose

The Scheduled Pipeline domain **orchestrates the content processing workflow** via cron jobs that call CMR API endpoints. These jobs trigger scraping, status checks, insight generation, and graph ingestion on a schedule.

## Core Behavior

1. **Resource scraper** (`cronjobs/resource_scraper/`):
   - POST `/resources/scrape` with `publication_days_back`, `limit` from config
   - Triggers creation of Apify scraping jobs for eligible resources

2. **Resource status & insight** (`cronjobs/resource_status_insight/`):
   - Step 1: GET `/resources/scrape/status` (limit, max_resurrection_attempts)
   - Step 2: Brief pause (2 seconds) — "allows immediate status updates"
   - Step 3: POST `/resources/insight` with publication_days_back, limit
   - Chains scrape status check → insight queue in one run

3. **Insight ingest** (`cronjobs/insight_ingest/`):
   - POST `/resources/insight/ingest` with publication_days_back, limit
   - Queues Graphiti processing for resources with insights

## Key Data

- **Config files**: JSON per job (e.g. `resource_scraper.json`, `resource_status_insight/config.json`)
- **Environment**: `CMR_API_BASE_URL`, `CMR_API_KEY` for API calls

## Boundaries

- **Depends on**: CMR API (all resource endpoints)
- **Depended on by**: None (orchestration only)

## Edge Cases and Notable Logic

- **2-second wait**: resource_status_insight waits 2s between scrape/status and insight — minimal; "next cron run will catch delayed completions"
- **No polling**: Status check doesn't poll until jobs complete; single check per run
- **Dry-run**: All jobs support `--dry-run` to skip API calls

## What to Preserve

- Separation of concerns: scraper, status+insight, ingest as distinct jobs
- Config-driven parameters (publication_days_back, limit)
- Simple HTTP client pattern (httpx, env-based URL/key)
