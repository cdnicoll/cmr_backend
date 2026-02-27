# Domain: Scraping

## Purpose

The Scraping domain orchestrates **web content extraction** via Apify. It identifies resources that need scraping, creates Apify jobs (grouped by type: website vs YouTube), and polls Apify to update the database when jobs complete.

## Core Behavior

1. **Create scraping jobs** (`POST /api/v1/resources/scrape`):
   - Queries resources where: `scrape=true`, no existing job OR job has no `data_id`, within `publication_days_back`
   - Groups by type (website, YouTube) — each group gets one Apify run
   - Creates Apify jobs, stores `jobs` records, links resources to jobs via `job_id`

2. **Check job status** (`GET /api/v1/resources/scrape/status`):
   - Finds pending jobs (no `data_id`) in DB
   - Calls Apify API to get run status
   - On success: updates `jobs.data_id` with Apify dataset ID
   - **Job resurrection**: Timed-out jobs can be "resurrected" (re-run) up to `max_resurrection_attempts`

3. **Eligibility rules**: Resource is eligible if:
   - `scrape = true`
   - `job_id IS NULL` OR (`job_id` exists AND `data_id IS NULL` — job not yet completed)
   - `created_at` within publication window

## Key Data

- **jobs table**: `id`, `job_id` (Apify run ID), `data_id` (Apify dataset ID when complete), `type` (apify), `resurrection_attempts`
- **ScrapeJobRequest**: `publication_days_back`, `limit`
- **JobStatusCheckRequest**: `limit`, `max_resurrection_attempts`

## Boundaries

- **Depends on**: Apify API, PostgreSQL (resource, jobs), ResourceService
- **Depended on by**: Insight processing (needs `data_id` to fetch scraped content)

## Edge Cases and Notable Logic

- **No eligible resources**: Returns 200 with empty response (`jobs_created: 0`), not 404
- **Apify errors**: Surfaces as 502 when "apify" or "rate limit" in error message
- **Job resurrection**: Timed-out runs can be retried; `resurrection_attempts` tracked
- **Grouping**: Website and YouTube use different Apify actors; one job per type per batch

## What to Preserve

- Eligibility criteria (scrape flag, job state, publication window)
- Grouping by content type for Apify actors
- Resurrection semantics for timed-out jobs
- 200 + empty response for "no work" (not 404)
