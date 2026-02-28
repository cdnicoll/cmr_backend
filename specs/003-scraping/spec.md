# Feature Specification: Phase 2 — Scraping (Crawl4AI Integration)

**Feature Branch**: `003-scraping`  
**Created**: 2025-02-27  
**Status**: Draft  
**Input**: `_local/build-plan.md` Phase 2, `_local/domain_findings/domains/02-scraping.md`, `_local/starter-kit/modal-jobs.md`, `_local/starter-kit/patterns.md`

## Summary

Phase 2 integrates **Crawl4AI** for web content extraction. A Modal scraping function accepts `resource_id`, fetches content (website or YouTube), stores it on the resource row, and transitions `pipeline_stage` from `discovered` → `scraping` → `scraped` (or `failed`). Apify, the jobs table for scraping, and status polling are removed. The scrape worker runs in the existing browser tier and is invoked directly via Modal CLI/dashboard (or by discovery in Phase 5).

## Clarifications (from build-plan.md)

- **Crawl4AI API**: Use Crawl4AI as a Python library inside the existing `browser` tier Modal function. Starter defines browser tier (2 CPU, 2GB, 5min timeout); add `browser_image` for Playwright/Chromium if needed.
- **Content storage**: Store raw scraped content as JSONB on the `resource` row (`scraped_content`). Simple and co-located.
- **Trigger**: No manual REST endpoint. The scrape Modal function is invoked directly via Modal CLI/dashboard. Phase 5 wires discovery to spawn it.

## User Scenarios & Testing

### User Story 1 — Scrape Website Resource (Priority: P1)

As the system (or a developer via Modal CLI), I need to run the scrape worker with a `resource_id` so website content is extracted and stored for downstream insight extraction.

**Independent Test**: Spawn scrape worker with a resource in `discovered` stage; confirm `pipeline_stage` → `scraped` and `scraped_content` populated.

**Acceptance Scenarios**:

1. **Given** a resource with `pipeline_stage = discovered` and `type = website`, **When** the scrape worker runs, **Then** the resource transitions `discovered` → `scraping` → `scraped` and `scraped_content` JSONB is populated
2. **Given** a resource with `type = youtube`, **When** the scrape worker runs, **Then** the YouTube extraction path runs and `scraped_content` is populated
3. **Given** a URL that blocks scrapers, **When** the scrape worker runs, **Then** `pipeline_stage = failed` and `failure_reason` is populated
4. **Given** a page that returns near-empty content (e.g. CAPTCHA, "please enable JavaScript" — word_count &lt; 50), **When** the scrape worker runs, **Then** `pipeline_stage = failed` and `failure_reason = "Insufficient content"`
5. **Given** a resource already in `scraped` or `complete`, **When** the scrape worker runs, **Then** it skips or fails gracefully (no overwrite of completed content)

---

### User Story 2 — Pipeline Stage Transitions (Priority: P1)

As the system, `pipeline_stage` must reflect scrape progress so downstream workers and recovery logic can reason about resource state.

**Independent Test**: Inspect resource row before/after scrape; confirm stage transitions and `updated_at` changes.

**Acceptance Scenarios**:

1. **Given** scrape starts, **Then** `pipeline_stage` is set to `scraping` atomically
2. **Given** scrape succeeds, **Then** `pipeline_stage` is set to `scraped`
3. **Given** scrape fails (timeout, block, error), **Then** `pipeline_stage` is set to `failed` and `failure_reason` contains error type and message

---

### User Story 3 — Timeouts and Retries (Priority: P2)

As the system, the scrape worker must respect timeouts and handle failures without leaving resources stuck in `scraping`.

**Independent Test**: Spawn against a slow or blocking URL; confirm failure handling.

**Acceptance Scenarios**:

1. **Given** a crawl exceeds the Modal function timeout (5 min), **Then** the resource is marked `failed` with a timeout reason (via Modal retry or explicit catch)
2. **Given** Crawl4AI raises an exception, **Then** the resource is marked `failed` with `failure_reason` populated

---

## Edge Cases (from domain findings)

- **Insufficient content**: Scrape succeeds technically but returns near-empty content (e.g. CAPTCHA page, "please enable JavaScript"). If `word_count < MIN_WORD_COUNT` (default 50), mark `failed` with `failure_reason = "Insufficient content"`. Catch at scrape time, not Phase 3.
- **No eligible resources**: N/A — worker is invoked with explicit `resource_id`; caller ensures eligibility
- **Website vs YouTube routing**: Preserve grouping by type; website uses Crawl4AI, YouTube uses separate extraction (e.g. youtube-transcript-api or Crawl4AI on YouTube page)
- **Job resurrection**: Legacy had resurrection for timed-out Apify jobs. New design: no automatic retry; manual re-queue only (Phase 8)
- **200 + empty for no work**: N/A — worker is invoked per-resource

## Requirements

### Functional Requirements

- **FR-001**: Modal scrape function MUST accept `resource_id` (UUID) and fetch the resource from Supabase
- **FR-002**: Scrape function MUST transition `pipeline_stage`: `discovered` → `scraping` at start, then `scraped` or `failed` on completion
- **FR-003**: Scrape function MUST store raw content in `scraped_content` JSONB on the resource row
- **FR-004**: Scrape function MUST populate `failure_reason` when `pipeline_stage = failed`
- **FR-005**: Website URLs MUST use Crawl4AI (`AsyncWebCrawler`) for content extraction
- **FR-006**: YouTube URLs MUST use a dedicated extraction path (youtube-transcript-api or equivalent)
- **FR-007**: Scrape function MUST run in the browser tier (Playwright/Chromium available for Crawl4AI)
- **FR-008**: Scrape function MUST handle timeouts and exceptions; never leave resource stuck in `scraping` without eventual `scraped` or `failed`
- **FR-009**: Scrape function MUST skip or fail gracefully when resource is not in `discovered` (e.g. already `scraped`)
- **FR-010**: Modal function decorator MUST use `retries=1` (one retry for transient failures; no retry logic inside the function)
- **FR-011**: Scrape function MUST validate minimum content length after extraction; if `word_count < MIN_WORD_COUNT` (default 50), mark `pipeline_stage = failed` with `failure_reason = "Insufficient content"`

### Key Entities

- **Resource** (existing): `id`, `url`, `type`, `pipeline_stage`, `failure_reason`, `scraped_content`, `updated_at`
- **Scraped content schema** (JSONB): `{ "markdown": "...", "title": "...", "metadata": {...} }` — structure TBD in research

## Success Criteria

- **SC-001**: Spawn scrape worker with `resource_id`; resource transitions to `scraped` with `scraped_content` populated
- **SC-002**: YouTube URL runs YouTube extraction path; content stored
- **SC-003**: Blocked/slow URL results in `pipeline_stage = failed` and `failure_reason` populated
- **SC-004**: No resources left stuck in `scraping` after worker completes (success or failure)
- **SC-005**: Near-empty content (word_count &lt; 50) results in `pipeline_stage = failed`, `failure_reason = "Insufficient content"`
