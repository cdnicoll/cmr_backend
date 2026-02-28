# Quickstart: Phase 2 — Scraping (Crawl4AI Integration)

**Target**: Developer runs the scrape worker via Modal after completing Phase 1 (Resources) setup.

---

## Prerequisites

Same as Phase 1, plus:

- **Phase 1 complete**: `resources` table exists; at least one resource with `pipeline_stage = discovered`
- **Modal account** — required for scrape worker (not optional)
- **Modal secrets**: `supabase-credentials-{ENV}`, `app-config-{ENV}` (same as starter)

**Optional env var**: `SCRAPE_MIN_WORD_COUNT` (default 50) — minimum word count for successful scrape; below this, mark `failed` with "Insufficient content"

---

## Setup

### 1. Install dependencies

```bash
uv add crawl4ai youtube-transcript-api
```

(Or add to `pyproject.toml` and run `uv sync`.)

### 2. Deploy workers

```bash
uv run deploy_dev
```

This deploys the Modal app including `scrape_resource`.

### 3. Create a test resource (if needed)

```bash
# Get JWT
export JWT_TOKEN=$(uv run python scripts/get_jwt.py)

# Create resource
curl -X POST http://localhost:8000/api/v1/resources \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
```

Note the `resource_id` from the response.

---

## Run Scrape Worker

### Via Modal CLI

```bash
modal run src.deployment.modal_workers::scrape_resource --resource-id "<resource-uuid>"
```

Replace `<resource-uuid>` with a resource in `discovered` stage.

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
| Check failure handling | Use a URL known to block scrapers; confirm `pipeline_stage = failed`, `failure_reason` populated |
| Check YouTube | Create resource with YouTube URL; run scrape; confirm `scraped_content.metadata.type = youtube` |

---

## Test Checklist (from build-plan)

- [ ] Spawn scrape worker with `resource_id` (resource in `discovered`); confirm `discovered` → `scraping` → `scraped`
- [ ] Confirm `scraped_content` JSONB populated on resource row
- [ ] Repeat with YouTube URL — confirm YouTube extraction path runs
- [ ] Spawn against URL that blocks scrapers — confirm `pipeline_stage = failed`, `failure_reason` populated
- [ ] Spawn against page with near-empty content (word_count &lt; 50) — confirm `pipeline_stage = failed`, `failure_reason = "Insufficient content"`

---

## Troubleshooting

- **Modal timeout**: 5 min default; long pages may timeout. Resource may stay `scraping` until recovery (Phase 8).
- **Crawl4AI/Playwright errors**: Ensure browser tier image includes Chromium. Run `crawl4ai-setup` in image build if needed.
- **YouTube "No transcript"**: Video may have captions disabled; resource will be marked `failed`.
- **Resource not found**: Ensure `resource_id` is a valid UUID and exists in `resources` table.
- **"Insufficient content"**: Page returned too little text (e.g. CAPTCHA, "please enable JavaScript"). Lower `SCRAPE_MIN_WORD_COUNT` to test, or use a different URL.
