# Data Model: Phase 2 — Scraping (Crawl4AI Integration)

**Feature**: 003-scraping  
**Date**: 2025-02-27 | **Phase**: 2

## Entities

### 1. Resource (extended)

No new table. The `resources` table (from Phase 1) is extended in usage:

| Field | Phase 2 Usage |
|-------|---------------|
| id | Input to scrape function |
| url | Passed to Crawl4AI or YouTube API |
| type | Routes to website vs YouTube extraction |
| pipeline_stage | Transitions: `discovered` → `scraping` → `scraped` or `failed` |
| failure_reason | Populated on failure |
| scraped_content | Populated on success (JSONB) |
| updated_at | Updated on each stage change |

**State transitions** (Phase 2):

- `discovered` → `scraping` (at scrape start; conditional on current stage)
- `scraping` → `scraped` (on success; word_count >= MIN_WORD_COUNT)
- `scraping` → `failed` (on error, timeout, block, or insufficient content)
- Skip if not `discovered` (e.g. already `scraped` or `complete`)

---

### 2. Scraped Content (JSONB schema)

Stored in `resources.scraped_content`. Not a separate table.

```json
{
  "markdown": "Full text content in Markdown format...",
  "title": "Page or video title",
  "url": "https://example.com/article",
  "extracted_at": "2025-02-27T12:00:00Z",
  "metadata": {
    "word_count": 1234,
    "type": "website"
  }
}
```

| Field | Type | Description |
|-------|------|--------------|
| markdown | string | Primary content; Markdown for websites, transcript for YouTube |
| title | string | Page title or video title |
| url | string | Source URL (denormalized for convenience) |
| extracted_at | string | ISO8601 timestamp |
| metadata | object | `word_count`, `type` (`website` \| `youtube`) |

**Validation**: Pydantic model `ScrapedContent` for serialization/validation before DB write.

---

## Validation Rules

### Resource (scrape eligibility)

- `pipeline_stage` MUST be `discovered` for scrape to start
- `type` MUST be `website` or `youtube` (from Phase 1)
- `url` MUST be non-null

### Scraped Content

- `markdown` MUST be non-empty on success
- `metadata.type` MUST match resource `type`
- `metadata.word_count` MUST be >= `MIN_WORD_COUNT` (default 50, env `SCRAPE_MIN_WORD_COUNT`) on success; otherwise treat as failed with `failure_reason = "Insufficient content"`

---

## Migration

**No new migration in Phase 2.** The `scraped_content` JSONB column exists from Phase 1. Phase 2 only writes to it.

---

## API Schemas (Pydantic)

### ScrapedContent

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScrapedContentMetadata(BaseModel):
    word_count: int
    type: Literal["website", "youtube"]

class ScrapedContent(BaseModel):
    markdown: str
    title: str
    url: str
    extracted_at: datetime
    metadata: ScrapedContentMetadata
```

### Scrape Function Signature

```python
@app.function(..., retries=1)
async def scrape_resource(resource_id: str) -> None:
    """Scrape a resource by ID. Updates pipeline_stage and scraped_content."""
```

Modal retries: `retries=1` — one retry for transient failures; avoids infinite loops on blocked sites.
