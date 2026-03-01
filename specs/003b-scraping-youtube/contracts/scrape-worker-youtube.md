# Scrape Worker Contract — YouTube Path (Phase 2b)

**Type**: Modal function (internal) — extends existing `scrape_resource`  
**Invocation**: `modal run` or `scrape_resource.spawn(resource_id)`  
**Auth**: Modal secrets (Supabase service role for DB access)

---

## scrape_resource(resource_id: str) — YouTube Path

When `resource.type = youtube`, the scrape function routes to the YouTube extraction path. This document describes the YouTube-specific behavior.

**Prerequisite**: Phase 2 `scrape_resource` exists. Phase 2b extends it to handle `type = youtube`.

### Parameters

| Name | Type | Required | Description |
|-----|------|----------|-------------|
| resource_id | str (UUID) | Yes | Primary key of the resource to scrape |

### Behavior (YouTube Path)

1. **Fetch resource**: Query `resources` by `id`. If not found, log and return.
2. **Eligibility check**: If `pipeline_stage != discovered`, skip (log and return).
3. **Type check**: If `type != youtube`, route to website path (Crawl4AI) — not Phase 2b scope.
4. **Transition to scraping**: Atomic update `pipeline_stage = scraping` where `id = resource_id` and `pipeline_stage = discovered`. If no rows updated, return.
5. **Extract transcript**:
   - Extract video ID from `url` (e.g. `https://www.youtube.com/watch?v=VIDEO_ID` or `https://youtu.be/VIDEO_ID`)
   - Call `youtube_transcript_api.YouTubeTranscriptApi.get_transcript(video_id)`
   - Concatenate transcript entries' `text` into markdown string
   - Compute `word_count` from `len(markdown.split())`
6. **Validate content length**: If `word_count < MIN_WORD_COUNT` (default 50, `SCRAPE_MIN_WORD_COUNT`), treat as failure → step 6 with `failure_reason = "Insufficient content"`.
7. **On success**: Update `pipeline_stage = scraped`, `scraped_content = <ScrapedContent JSON>` with `metadata.type = "youtube"`.
8. **On failure**: Update `pipeline_stage = failed`, `failure_reason = "{ErrorType}: {message}"` (or `"Insufficient content"` for length validation)

### ScrapedContent JSONB Structure (YouTube)

```json
{
  "markdown": "Transcript line 1\nTranscript line 2\n...",
  "title": "Video title or URL fallback",
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "extracted_at": "ISO8601",
  "metadata": { "word_count": 1234, "type": "youtube" }
}
```

### Errors (YouTube)

- **Resource not found**: Log; return (no exception)
- **Insufficient content** (word_count < MIN_WORD_COUNT): Mark `failed` with `failure_reason = "Insufficient content"`
- **Not eligible** (stage != discovered): Log; return
- **TranscriptsDisabled**: Captions disabled by uploader; mark `failed` with `failure_reason`
- **VideoUnavailable**: Video private/deleted/region-restricted; mark `failed` with `failure_reason`
- **NoTranscriptFound**: No captions available; mark `failed` with `failure_reason`
- **HTTPError / other**: Catch; mark `failed` with `failure_reason`
- **Modal timeout** (5 min): Process killed; resource may remain `scraping` until recovery (Phase 8)

### Return

`None` (void). Side effects: DB updates only.

---

## Invocation Examples

Same as Phase 2. No change to invocation.

### Modal CLI

```bash
modal run src.deployment.modal_workers::scrape_resource --resource-id "<uuid>"
```

### From Python (e.g. discovery in Phase 5)

```python
from src.deployment.modal_workers import scrape_resource
scrape_resource.spawn("<resource-uuid>")
```

---

## Configuration

- `SCRAPE_MIN_WORD_COUNT` (optional, default 50): Minimum word count for successful scrape; below this, mark `failed` with "Insufficient content"

## Dependencies

- Supabase client (service role) — from Modal secrets
- youtube-transcript-api — for YouTube transcript extraction
- No browser required for YouTube path (unlike Crawl4AI website path)
