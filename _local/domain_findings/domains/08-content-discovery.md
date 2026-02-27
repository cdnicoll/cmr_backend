# Domain: Content Discovery (Cron)

## Purpose

The Content Discovery domain **automatically discovers URLs** from mining industry sources (sitemaps, RSS feeds) and submits them to the CMR API for resource creation. Runs as a standalone cron job, typically daily.

## Core Behavior

1. **Sitemap scanner** (`cronjobs/sitemap_scanner/`):
   - Loads config: sources (sitemap or RSS), settings (days_back, batch_size, etc.)
   - For each enabled source:
     - **Sitemap**: Discovers sitemaps, parses URLs, filters by date/relevance/domain rules, deduplicates
     - **RSS**: Parses configured feeds, filters by date, relevance, deduplicates
   - Submits URLs in batches via `POST /api/v1/resources` (CMR API)
   - Dry-run mode: skips actual API submission

2. **URL filtering**:
   - **Date**: `days_back_filter` — keep URLs from last N days
   - **Relevance**: `min_relevance_score`, optional custom patterns per source
   - **Domain rules**: required_path_patterns, excluded_path_patterns, max_path_depth, require_https

3. **RSS support**: Uses `feedparser`; sources with `known_rss_feeds` are processed as RSS; discovery "not yet implemented"

## Key Data

- **Config**: JSON with `sources` (base_url, type, known_sitemaps, known_rss_feeds, url_filtering), `settings`
- **SourceType**: sitemap, rss
- **SitemapJobResult**: success, total_urls_submitted, source_results, errors

## Boundaries

- **Depends on**: CMR API (resources endpoint), httpx, feedparser, sitemap parser
- **Depended on by**: None (feeds into Resources domain via API)

## Edge Cases and Notable Logic

- **Config path**: Default `cronjobs/config/sitemap_sources.json`; env-specific overrides
- **RSS discovery**: Not implemented — requires explicit `known_rss_feeds`
- **Batch submission**: Uses `batch_size` (default 50); API returns created count
- **Error handling**: Per-source errors don't fail job; `ErrorSeverity.FATAL` does

## What to Preserve

- Sitemap + RSS as dual discovery mechanisms
- Filter pipeline: date → relevance → domain rules → deduplication
- Batch submission to API
- Dry-run for testing
