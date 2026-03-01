# Data Model: Phase 2b — YouTube Scraping

**Feature**: 003b-scraping-youtube  
**Date**: 2025-02-27 | **Phase**: 2b

## Entities

### 1. Resource (extended)

No new table. The `resources` table (from Phase 1) is used identically to Phase 2:

| Field | Phase 2b Usage |
|-------|----------------|
| id | Input to scrape function |
| url | Passed to youtube-transcript-api (extract video ID) |
| type | Routes to YouTube extraction when `type = youtube` |
| pipeline_stage | Transitions: `discovered` → `scraping` → `scraped` or `failed` |
| failure_reason | Populated on failure |
| scraped_content | Populated on success (JSONB) |
| updated_at | Updated on each stage change |

**State transitions** (Phase 2b — same as Phase 2):

- `discovered` → `scraping` (at scrape start; conditional on current stage)
- `scraping` → `scraped` (on success; word_count >= MIN_WORD_COUNT)
- `scraping` → `failed` (on error, disabled captions, unavailable video, or insufficient content)
- Skip if not `discovered` (e.g. already `scraped` or `complete`)

---

### 2. Scraped Content (JSONB schema) — YouTube

Stored in `resources.scraped_content`. Same structure as Phase 2; `metadata.type = "youtube"`.

```json
{
  "markdown": "Transcript line 1\nTranscript line 2\n...",
  "title": "Video title or fallback",
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "extracted_at": "2025-02-27T12:00:00Z",
  "metadata": {
    "word_count": 1234,
    "type": "youtube"
  }
}
```

| Field | Type | Description |
|-------|------|--------------|
| markdown | string | Primary content; concatenated transcript text |
| title | string | Video title if available; else fallback (e.g. URL) |
| url | string | Source URL (denormalized for convenience) |
| extracted_at | string | ISO8601 timestamp |
| metadata | object | `word_count`, `type` = `youtube` |

**Validation**: Same Pydantic model `ScrapedContent` from Phase 2; `metadata.type` = `"youtube"` for YouTube resources.

---

## Validation Rules

### Resource (scrape eligibility)

- `pipeline_stage` MUST be `discovered` for scrape to start
- `type` MUST be `youtube` for YouTube path (Phase 2b scope)
- `url` MUST be non-null and contain valid YouTube video ID

### Scraped Content (YouTube)

- `markdown` MUST be non-empty on success
- `metadata.type` MUST be `youtube`
- `metadata.word_count` MUST be >= `MIN_WORD_COUNT` (default 50, env `SCRAPE_MIN_WORD_COUNT`) on success; otherwise treat as failed with `failure_reason = "Insufficient content"`

---

## Migration

**No new migration in Phase 2b.** The `scraped_content` JSONB column exists from Phase 1. Phase 2b only writes to it (YouTube path).

---

## API Schemas (Pydantic)

### ScrapedContent

Same as Phase 2. `ScrapedContent` and `ScrapedContentMetadata` already support `type: Literal["website", "youtube"]`.

### Scrape Function Signature

```python
@app.function(..., retries=1)
async def scrape_resource(resource_id: str) -> None:
    """Scrape a resource by ID. Routes by type: website → Crawl4AI, youtube → youtube-transcript-api."""
```

No signature change. Phase 2b extends internal routing logic.
