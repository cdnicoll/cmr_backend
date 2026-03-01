# Feature Specification: Phase 2b — YouTube Scraping

**Feature Branch**: `003b-scraping-youtube`  
**Created**: 2025-02-27  
**Status**: Draft  
**Input**: `_local/build-plan.md` Phase 2b, `_local/domain_findings/domains/02-scraping.md`, `_local/starter-kit/patterns.md`, `_local/starter-kit/modal-jobs.md`, `specs/003-scraping/`

## Summary

Phase 2b extends the existing `scrape_resource` Modal function to handle `type = youtube` resources using `youtube-transcript-api`. Crawl4AI does not support YouTube. The extraction path, `scraped_content` JSONB schema, `pipeline_stage` transitions, and failure handling are identical to Phase 2 — only the extraction library differs. No new tables, no new Modal functions.

## Clarifications (from build-plan.md)

- **YouTube extraction library**: Use `youtube-transcript-api`. Crawl4AI does not support YouTube. Fetches captions directly from YouTube's caption API — lightweight, no browser required, raises clear exceptions when captions are unavailable.
- **Scrape worker concurrency**: `max_containers = 8` on `scrape_resource` (from Phase 2). Modal queues spawns beyond 8; applies to both website and YouTube scraping.
- **Scope**: Phase 2b only — extend existing `scrape_resource`; no new infrastructure.

## User Scenarios & Testing

### User Story 1 — Scrape YouTube Resource (Priority: P1)

As the system (or a developer via Modal CLI), I need to run the scrape worker with a `resource_id` for a YouTube URL so transcript content is extracted and stored for downstream insight extraction.

**Independent Test**: Create resource with YouTube URL (`pipeline_stage = discovered`); spawn scrape worker; confirm `pipeline_stage` → `scraped` and `scraped_content` populated with transcript.

**Acceptance Scenarios**:

1. **Given** a resource with `pipeline_stage = discovered` and `type = youtube`, **When** the scrape worker runs, **Then** the resource transitions `discovered` → `scraping` → `scraped` and `scraped_content.markdown` contains the transcript
2. **Given** a YouTube video with captions available, **When** the scrape worker runs, **Then** `scraped_content.metadata.type = youtube` and `metadata.word_count` >= `SCRAPE_MIN_WORD_COUNT`
3. **Given** a YouTube video with disabled or unavailable captions, **When** the scrape worker runs, **Then** `pipeline_stage = failed` and `failure_reason` is populated
4. **Given** transcript word_count < `SCRAPE_MIN_WORD_COUNT`, **When** the scrape worker runs, **Then** `pipeline_stage = failed` and `failure_reason = "Insufficient content"`
5. **Given** a resource already in `scraped` or `complete`, **When** the scrape worker runs, **Then** it skips (no overwrite of completed content)

---

### User Story 2 — Pipeline Stage Transitions (Priority: P1)

As the system, `pipeline_stage` must reflect scrape progress so downstream workers and recovery logic can reason about resource state.

**Independent Test**: Inspect resource row before/after scrape; confirm stage transitions and `updated_at` changes.

**Acceptance Scenarios**:

1. **Given** scrape starts for YouTube resource, **Then** `pipeline_stage` is set to `scraping` atomically
2. **Given** scrape succeeds, **Then** `pipeline_stage` is set to `scraped`
3. **Given** scrape fails (disabled captions, unavailable, error), **Then** `pipeline_stage` is set to `failed` and `failure_reason` contains error type and message

---

## Edge Cases (from domain findings)

- **Disabled captions**: `youtube-transcript-api` raises `TranscriptsDisabled` or similar; catch and mark `failed` with `failure_reason`
- **Video unavailable / private**: API raises; mark `failed` with `failure_reason`
- **Insufficient content**: Same as Phase 2 — if `word_count < SCRAPE_MIN_WORD_COUNT`, mark `failed` with `failure_reason = "Insufficient content"`
- **No eligible resources**: N/A — worker is invoked with explicit `resource_id`; caller ensures eligibility
- **Website vs YouTube routing**: Preserve grouping by type; Phase 2b adds/extends the YouTube path in `scrape_resource`

## Requirements

### Functional Requirements

- **FR-001**: `scrape_resource` MUST route `type = youtube` resources to the YouTube extraction path
- **FR-002**: YouTube extraction MUST use `youtube-transcript-api` to fetch transcript
- **FR-003**: YouTube transcript MUST be stored in `scraped_content` JSONB with `metadata.type = youtube`
- **FR-004**: Scrape function MUST populate `failure_reason` when `pipeline_stage = failed` (disabled captions, unavailable, insufficient content)
- **FR-005**: Same `pipeline_stage` transitions as Phase 2: `discovered` → `scraping` → `scraped` or `failed`
- **FR-006**: Same minimum content length validation: `word_count >= SCRAPE_MIN_WORD_COUNT`; otherwise `failed` with `failure_reason = "Insufficient content"`
- **FR-007**: Same eligibility check: skip if `pipeline_stage != discovered`

### Key Entities

- **Resource** (existing): `id`, `url`, `type`, `pipeline_stage`, `failure_reason`, `scraped_content`, `updated_at`
- **Scraped content schema** (JSONB): `{ "markdown": "...", "title": "...", "metadata": { "word_count": N, "type": "youtube" } }` — same as Phase 2

## Success Criteria

- **SC-001**: Spawn scrape worker with YouTube resource `resource_id`; resource transitions to `scraped` with `scraped_content` populated
- **SC-002**: `scraped_content.metadata.type = youtube`
- **SC-003**: Video with disabled captions results in `pipeline_stage = failed` and `failure_reason` populated
- **SC-004**: No resources left stuck in `scraping` after worker completes (success or failure)
- **SC-005**: Near-empty transcript (word_count < 50) results in `pipeline_stage = failed`, `failure_reason = "Insufficient content"`
