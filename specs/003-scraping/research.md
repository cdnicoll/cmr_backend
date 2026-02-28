# Research: Phase 2 — Scraping (Crawl4AI Integration)

**Feature**: 003-scraping  
**Date**: 2025-02-27 | **Phase**: 0

## Context

Phase 2 integrates Crawl4AI for web content extraction. The build plan and domain findings provide scope. This document consolidates decisions for traceability.

---

## 1. Crawl4AI Integration

**Decision**: Use Crawl4AI as a Python library (`crawl4ai`) with `AsyncWebCrawler`. Run inside the existing browser-tier Modal function. Use `BrowserConfig(headless=True)` and `CrawlerRunConfig(cache_mode=CacheMode.BYPASS)` for fresh content. Extract Markdown via default `result.markdown` (or `result.markdown.raw_markdown`).

**Rationale**: Crawl4AI is LLM-friendly, supports dynamic JS pages, and produces Markdown suitable for downstream insight extraction. Async API fits Modal's async-native workers.

**Alternatives considered**:
- Apify: Removed per build plan; external dependency and polling.
- BeautifulSoup/httpx: No JS rendering; insufficient for dynamic sites.
- Playwright directly: Crawl4AI wraps Playwright with extraction and Markdown generation; less custom code.

**Implementation notes**: Add `crawl4ai` to Modal image. Crawl4AI uses Playwright; ensure `browser_image` or base image includes Chromium. Run `crawl4ai-setup` in image build if required.

---

## 2. Modal Image and Browser Tier

**Decision**: Extend the existing `process_browser_job` image with `crawl4ai` and Playwright dependencies. The starter's modal-jobs.md references `browser_image`; the current codebase uses a single `image` for all tiers. Add `crawl4ai` and `playwright` to the browser-tier image. If Crawl4AI requires `crawl4ai-setup`, run it in the image build step.

**Rationale**: Crawl4AI launches a headless Chromium; Playwright must be installed. The scrape function will run in the same tier as `process_browser_job` (2 CPU, 2GB, 5 min timeout).

**Alternatives considered**:
- Separate `browser_image` with Playwright pre-installed: Aligns with starter-kit; use if base image lacks Chromium.
- GPU tier: Overkill; Crawl4AI does not require GPU.

---

## 3. Scrape Function Invocation (Not Job Queue)

**Decision**: Implement a standalone Modal function `scrape_resource(resource_id: str)` that is invoked directly via `modal run` or `scrape_resource.spawn(resource_id)`. Do NOT add a job type to the jobs table. Discovery (Phase 5) will spawn this function directly for each new resource.

**Rationale**: Build plan explicitly states "Removal of Apify, jobs table for scraping, and status polling." Resource state lives on the resource row (`pipeline_stage`); no need for a separate job record.

**Alternatives considered**:
- Add `resource_scrape` job type: Would require jobs table; build plan removes jobs for scraping.
- REST endpoint `POST /resources/scrape`: Build plan says no manual trigger; Modal CLI suffices.

---

## 4. Scraped Content Schema (JSONB)

**Decision**: Store scraped content as JSONB with structure:
```json
{
  "markdown": "...",
  "title": "...",
  "url": "...",
  "extracted_at": "ISO8601",
  "metadata": { "word_count": 1234, "type": "website" | "youtube" }
}
```

**Rationale**: Markdown is primary for downstream LLM/insight extraction. Title and URL aid debugging. Metadata supports filtering (e.g. min word count in Phase 3).

**Alternatives considered**:
- Raw HTML: Heavier; Markdown is sufficient for insight extraction.
- Separate table: Build plan resolved — store on resource; co-located.

---

## 5. YouTube Extraction

**Decision**: Use `youtube-transcript-api` (or equivalent) for YouTube URLs. Crawl4AI is optimized for web pages; YouTube transcripts are fetched via YouTube's caption API. Store in same `scraped_content` schema with `metadata.type = "youtube"` and `markdown` as transcript text.

**Rationale**: Domain findings require "YouTube vs website routing"; YouTube uses different extraction. `youtube-transcript-api` is lightweight and well-maintained.

**Alternatives considered**:
- Crawl4AI on YouTube page: May work but YouTube pages are heavy; transcript API is direct.
- pytube: Broader scope (download); transcript API is focused.

**Implementation notes**: Add `youtube-transcript-api` to dependencies. Handle videos with disabled captions — mark `failed` with `failure_reason`.

---

## 6. Pipeline Stage Transitions and Atomicity

**Decision**: Use a single Supabase update at start to set `pipeline_stage = scraping`. On success: update to `scraped` + `scraped_content`. On failure: update to `failed` + `failure_reason`. Use `ResourcesDAO` (or equivalent) with `eq("id", resource_id).eq("pipeline_stage", "discovered")` for the initial transition to prevent double-processing.

**Rationale**: Atomic selection + update prevents race when discovery spawns multiple scrapes (Phase 5). Only transition from `discovered` to `scraping`; if already `scraped`, skip.

**Alternatives considered**:
- Optimistic locking with `updated_at`: Adds complexity; single conditional update suffices.
- Lock row: Overkill for Phase 2; conditional update is sufficient.

---

## 7. Failure Handling and Timeouts

**Decision**: Wrap Crawl4AI/YouTube calls in try/except. On exception: set `pipeline_stage = failed`, `failure_reason = f"{type(e).__name__}: {str(e)}"`. Modal function timeout (5 min) will kill the process; ensure we catch and mark failed before timeout when possible. For Modal timeout: resource may remain `scraping` until recovery worker (Phase 8) resets stuck resources.

**Rationale**: Build plan specifies "Modal function must handle timeouts, retries, and failure marking." Phase 8 adds recovery for stuck `scraping`; Phase 2 ensures explicit failures are marked.

**Alternatives considered**:
- Modal retries: **RESOLVED** — Use `retries=1` on the Modal function decorator. One retry for transient failures; avoids infinite loops on blocked sites. Build plan: "Modal-level retries, no retry logic inside the agent."
- Always mark failed on timeout: Modal doesn't guarantee cleanup; recovery worker handles stuck.

---

## 8. Minimum Content Length

**Decision**: After extraction, validate `word_count` against `MIN_WORD_COUNT` (env var, default 50). If `word_count < MIN_WORD_COUNT`, treat as failure: set `pipeline_stage = failed`, `failure_reason = "Insufficient content"`. Do not store scraped_content.

**Rationale**: Pages that block with CAPTCHA or "please enable JavaScript" return technically successful scrapes with near-empty content. Phase 3's insight extraction needs meaningful content; better to catch at scrape time than defer. Build plan flags "content validation (min length)" for Phase 3 — address it here.

**Alternatives considered**:
- Defer to Phase 3: Rejected; same validation would run there; catch earlier for clearer failure semantics.
- Store anyway, let Phase 3 fail: Rejected; wastes downstream processing; `failed` with clear reason is more actionable.

**Implementation notes**: Compute `word_count` from `len(markdown.split())` or equivalent before writing. Configurable via `SCRAPE_MIN_WORD_COUNT` env var.

---

## Summary

| Area | Decision | Key Rationale |
|------|----------|---------------|
| Crawl4AI | AsyncWebCrawler, Markdown output | LLM-friendly, dynamic pages |
| Modal image | Add crawl4ai, playwright to browser tier | Chromium required |
| Invocation | Standalone `scrape_resource(resource_id)` | No jobs table for scraping |
| Scraped schema | markdown, title, url, extracted_at, metadata | Downstream insight extraction |
| YouTube | youtube-transcript-api | Dedicated path per domain findings |
| Atomicity | Conditional update discovered→scraping | Race prevention |
| Failure | try/except, failure_reason | Explicit failure marking |
| Modal retries | retries=1 on decorator | One retry for transient; no loop on blocked sites |
| Min content | word_count >= 50 (configurable) | Catch CAPTCHA/blocked pages at scrape time |
