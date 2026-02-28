# Scrape Worker Contract

**Type**: Modal function (internal)  
**Invocation**: `modal run` or `scrape_resource.spawn(resource_id)`  
**Auth**: Modal secrets (Supabase service role for DB access)

---

## scrape_resource(resource_id: str)

Scrapes a single resource by ID. Fetches the resource from Supabase, routes by type (website vs YouTube), extracts content, and updates the resource row.

**Modal decorator**: `@app.function(..., retries=1)` — one retry for transient failures; avoids infinite loops on blocked sites. No retry logic inside the function.

### Parameters

| Name | Type | Required | Description |
|-----|------|----------|-------------|
| resource_id | str (UUID) | Yes | Primary key of the resource to scrape |

### Behavior

1. **Fetch resource**: Query `resources` by `id`. If not found, log and return.
2. **Eligibility check**: If `pipeline_stage != discovered`, skip (log and return). No overwrite of completed content.
3. **Transition to scraping**: Atomic update `pipeline_stage = scraping` where `id = resource_id` and `pipeline_stage = discovered`. If no rows updated, another worker may have claimed it; return.
4. **Extract content**:
   - **Website** (`type = website`): Run Crawl4AI `AsyncWebCrawler.arun(url)`, use `result.markdown`
   - **YouTube** (`type = youtube`): Run `youtube-transcript-api` (or equivalent), concatenate transcript as markdown
5. **Validate content length**: If `word_count < MIN_WORD_COUNT` (default 50, configurable via `SCRAPE_MIN_WORD_COUNT`), treat as failure → step 6 with `failure_reason = "Insufficient content"`. Do not store scraped_content.
6. **On success**: Update `pipeline_stage = scraped`, `scraped_content = <ScrapedContent JSON>`
7. **On failure**: Update `pipeline_stage = failed`, `failure_reason = "{ErrorType}: {message}"` (or `"Insufficient content"` for length validation)

### ScrapedContent JSONB Structure

```json
{
  "markdown": "...",
  "title": "...",
  "url": "...",
  "extracted_at": "ISO8601",
  "metadata": { "word_count": 1234, "type": "website" | "youtube" }
}
```

### Errors

- **Resource not found**: Log; return (no exception)
- **Insufficient content** (word_count &lt; MIN_WORD_COUNT): Mark `failed` with `failure_reason = "Insufficient content"`
- **Not eligible** (stage != discovered): Log; return
- **Crawl4AI/YouTube exception**: Catch; mark `failed` with `failure_reason`
- **Modal timeout** (5 min): Process killed; resource may remain `scraping` until recovery (Phase 8)

### Return

`None` (void). Side effects: DB updates only.

---

## Invocation Examples

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
- Crawl4AI — for website extraction
- youtube-transcript-api — for YouTube extraction
- Browser tier image — Playwright/Chromium for Crawl4AI
