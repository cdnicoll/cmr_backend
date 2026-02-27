# Domain: Resources

## Purpose

The Resources domain is responsible for **URL lifecycle management** — accepting, validating, storing, and tracking web content sources (articles, videos) that CMR will eventually scrape and analyze. It is the entry point for all content into the pipeline.

## Core Behavior

1. **Batch creation**: Accepts arrays of URLs via `POST /api/v1/resources`. Each URL is validated for security (SSRF protection), format, and type (website vs YouTube). Duplicates are skipped; new resources are inserted into the `resource` table.

2. **URL validation**: Uses `url_validation.py` for:
   - SSRF protection (blocks internal IPs, localhost, private ranges)
   - URL normalization (scheme, trailing slashes)
   - Type detection (website vs YouTube)
   - YouTube-specific format validation

3. **Resource lifecycle**: Resources move through states:
   - Created (no job) → Scraped (job with `data_id`) → Insight extracted → Graphiti ingested
   - Status columns (`insight_status`, `graphiti_status`) prevent race conditions during parallel processing

## Key Data

- **resource table**: `id`, `url` (unique), `title`, `type` (youtube|website), `scrape` (bool), `job_id` (FK to jobs), `channel`, `insight` (JSONB), `insight_status`, `graphiti_status`, `graphiti_ingested_at`, `created_at`, `updated_at`
- **ScrapeType enum**: `youtube`, `website`
- **BatchCreateResourceResponse**: `created`, `skipped`, `errors`, `results` (per-URL status)

## Boundaries

- **Depends on**: PostgreSQL (resource table), URL validation utils
- **Depended on by**: Scraping (finds eligible resources), Insights (processes scraped resources), Graphiti (ingests resources with insights)

## Edge Cases and Notable Logic

- **Duplicate handling**: Same URL returns "skipped" with existing `resource_id` — no error
- **Validation failures**: Individual URL errors don't fail the batch; each result has `status: created|skipped|error`
- **Bearer token**: Uses `Authorization: Bearer <api_key>` — note: some docs say "Bearer" but implementation uses `credentials.credentials` directly

## What to Preserve

- SSRF protection and URL validation rules
- Duplicate-by-URL semantics (skip, don't error)
- Batch response structure with per-URL results
- Resource type detection (website vs YouTube) for downstream routing
