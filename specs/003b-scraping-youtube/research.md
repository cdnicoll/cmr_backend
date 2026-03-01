# Research: Phase 2b — YouTube Scraping

**Feature**: 003b-scraping-youtube  
**Date**: 2025-02-27 | **Phase**: 0

## Context

Phase 2b extends the existing `scrape_resource` Modal function to handle `type = youtube` resources. Phase 2 (003-scraping) already researched Crawl4AI, scraped content schema, and pipeline transitions. This document consolidates YouTube-specific decisions.

---

## 1. YouTube Extraction Library

**Decision**: Use `youtube-transcript-api`. Crawl4AI does not support YouTube. Fetches captions directly from YouTube's caption API — lightweight, no browser required, raises clear exceptions when captions are unavailable.

**Rationale**: Build plan resolved: "Use youtube-transcript-api. Crawl4AI does not support YouTube." Phase 2 research.md already documented this. Library is well-maintained, synchronous API, easy to wrap in async.

**Alternatives considered**:
- Crawl4AI on YouTube page: Rejected — Crawl4AI does not support YouTube; YouTube pages are heavy.
- pytube: Broader scope (download); transcript API is focused on captions only.

**Implementation notes**: Add `youtube-transcript-api` to dependencies if not already present from Phase 2. Extract video ID from URL (e.g. `https://www.youtube.com/watch?v=VIDEO_ID` or `https://youtu.be/VIDEO_ID`). Handle `TranscriptsDisabled`, `VideoUnavailable`, `NoTranscriptFound` exceptions.

---

## 2. Scraped Content Schema (YouTube)

**Decision**: Same JSONB schema as Phase 2. `metadata.type = "youtube"`; `markdown` contains concatenated transcript text; `title` from video metadata if available, else fallback; `url` from resource.

**Rationale**: Phase 2 established `scraped_content` schema. Downstream insight extraction (Phase 3) expects the same structure regardless of source type.

**Alternatives considered**:
- Different schema for YouTube: Rejected — would require Phase 3 to handle two formats.
- Raw transcript format: Rejected — Markdown is preferred for downstream LLM.

**Implementation notes**: Transcript entries from `youtube-transcript-api` have `text` and `start`. Concatenate `text` with newlines; `word_count` = `len(markdown.split())`.

---

## 3. Failure Handling (YouTube)

**Decision**: Same failure handling as Phase 2. On exception: `pipeline_stage = failed`, `failure_reason = f"{type(e).__name__}: {str(e)}"`. On insufficient content: `failure_reason = "Insufficient content"`.

**Rationale**: Build plan: "Handle videos with disabled or unavailable captions → pipeline_stage = failed, failure_reason populated."

**Exceptions to handle**:
- `TranscriptsDisabled`: Captions disabled by uploader
- `VideoUnavailable`: Video private, deleted, or region-restricted
- `NoTranscriptFound`: No captions available
- `HTTPError`: Network/API errors

**Alternatives considered**:
- Retry on transient errors: Phase 2 uses Modal `retries=1`; no additional retry logic inside function.

---

## 4. Modal Tier for YouTube Path

**Decision**: YouTube path can run in the same `scrape_resource` function as website path. No browser required for YouTube — `youtube-transcript-api` uses HTTP only. If `scrape_resource` uses `browser_image` for Crawl4AI, the YouTube path still runs in that image; no separate tier needed.

**Rationale**: Single function, single invocation; routing by `type` is simpler than splitting into two Modal functions.

**Alternatives considered**:
- Separate Modal function for YouTube: Rejected — build plan: "No new Modal functions."
- Lighter tier for YouTube: Overkill — same image is fine; YouTube path is fast.

---

## Summary

| Area | Decision | Key Rationale |
|------|----------|---------------|
| Library | youtube-transcript-api | Crawl4AI doesn't support YouTube; lightweight |
| Schema | Same as Phase 2, metadata.type=youtube | Downstream consistency |
| Failure | Same as Phase 2; handle TranscriptsDisabled, etc. | Explicit failure marking |
| Modal tier | Same scrape_resource; no new function | Build plan: no new Modal functions |
