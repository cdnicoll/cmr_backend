# Quickstart: Phase 2b — YouTube Scraping

**Target**: Developer runs the scrape worker via Modal for YouTube resources after completing Phase 2 (Website Scraping) setup.

---

## Prerequisites

Same as Phase 2, plus:

- **Phase 2 complete**: `scrape_resource` Modal function exists; website scraping works
- **Phase 1 complete**: `resources` table exists; at least one resource with `pipeline_stage = discovered` and `type = youtube`
- **Modal account** — required for scrape worker (not optional)
- **Modal secrets**: `supabase-credentials-{ENV}`, `app-config-{ENV}` (same as starter)

**Optional env var**: `SCRAPE_MIN_WORD_COUNT` (default 50) — minimum word count for successful scrape; below this, mark `failed` with "Insufficient content"

---

## Setup

### 1. Install dependencies

```bash
uv add youtube-transcript-api
```

(Or add to `pyproject.toml` and run `uv sync`.)

### 2. Deploy workers

```bash
uv run deploy_dev
```

This deploys the Modal app including `scrape_resource` with YouTube path.

### 3. Create a test resource (YouTube URL)

```bash
# Get JWT
export JWT_TOKEN=$(uv run python scripts/get_jwt.py)

# Create resource with YouTube URL
curl -X POST http://localhost:8000/api/v1/resources \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]}'
```

Note the `resource_id` from the response. Resource should have `type = youtube` and `pipeline_stage = discovered`.

---

## Run Scrape Worker

### Via Modal CLI

```bash
modal run src.deployment.modal_workers::scrape_resource --resource-id "<resource-uuid>"
```

Replace `<resource-uuid>` with a YouTube resource in `discovered` stage.

### Via Modal Dashboard

1. Open Modal dashboard
2. Find the `Job-Worker-{ENV}` app
3. Select `scrape_resource` function
4. Enter `resource_id` as argument
5. Run

---

## Verify

| Action | How |
|--------|-----|
| Check resource in Supabase | Query `resources` where `id = <resource_id>`; confirm `pipeline_stage = scraped`, `scraped_content` populated |
| Check metadata | Confirm `scraped_content.metadata.type = youtube` |
| Check failure handling | Use a YouTube video with disabled captions; confirm `pipeline_stage = failed`, `failure_reason` populated |
| Check insufficient content | Use a very short video (e.g. < 50 words transcript); confirm `pipeline_stage = failed`, `failure_reason = "Insufficient content"` |

---

## Test Checklist (from build-plan)

- [ ] Create a resource with a YouTube URL (`pipeline_stage = discovered`)
- [ ] Spawn `scrape_resource` with the YouTube resource ID via Modal CLI/dashboard
- [ ] Confirm `pipeline_stage = scraped` and `scraped_content.markdown` contains the transcript
- [ ] Confirm `scraped_content.metadata.type = youtube`
- [ ] Spawn against a YouTube video with disabled captions — confirm `pipeline_stage = failed` and `failure_reason` populated

---

## Troubleshooting

- **Modal timeout**: 5 min default; YouTube transcript API is fast; unlikely to timeout.
- **"No transcript" / TranscriptsDisabled**: Video may have captions disabled; resource will be marked `failed`.
- **Video unavailable**: Video may be private, deleted, or region-restricted; resource will be marked `failed`.
- **Resource not found**: Ensure `resource_id` is a valid UUID and exists in `resources` table.
- **"Insufficient content"**: Transcript has very few words (< 50). Lower `SCRAPE_MIN_WORD_COUNT` to test, or use a different video.
- **Invalid video ID**: Ensure URL format is supported (e.g. `youtube.com/watch?v=ID` or `youtu.be/ID`).
