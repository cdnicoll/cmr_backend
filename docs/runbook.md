# CMR Backend — Developer Runbook

Commands for testing individual pipeline stages. No explanations — see `_local/` and `specs/` for context.

---

## Setup (one-time)

```bash
uv sync
cp .env.example .env   # fill in credentials
uv run python scripts/migrate.py
```

---

## JWT

Required for API endpoints. Reads `SUPABASE_USER_EMAIL` and `SUPABASE_USER_PASS` from `.env`.

```bash
eval $(uv run python scripts/get_jwt.py | grep "^export")
# JWT_TOKEN is now set in your shell
```

---

## Deploy

Pushes secrets from `.env` to Modal secrets, then deploys API and workers.

```bash
uv run deploy_dev    # develop
uv run deploy_prod   # production
```

**New env vars**: Add to both `.env` and `push_modal_secrets()` in `src/deployment/deploy.py`.

---

## Pillars

### Resources

```bash
# Start API locally
uv run python scripts/dev.py

# Create resources
curl -X POST http://localhost:8000/api/v1/resources \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/article", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]}'
```

**Verify**: Supabase `resources` — new rows with `pipeline_stage = discovered`, `type = website` or `youtube`.

**Failures**:
- `401` — JWT missing or expired; re-run `get_jwt.py`
- `422` — invalid URL format or SSRF-blocked IP range

---

### Scrape: Website (Crawl4AI)

```bash
modal run src.deployment.modal_workers::scrape_resource --resource-id "<uuid>"
```

Resource must have `pipeline_stage = discovered` and `type = website`.

**Verify**: Supabase `resources` — `pipeline_stage = scraped`, `scraped_content.metadata.type = website`.

**Failures**:
- `pipeline_stage = failed`, `failure_reason = "Insufficient content"` — page returned < 50 words (CAPTCHA, JS wall); try a different URL
- `pipeline_stage = failed`, other `failure_reason` — Crawl4AI/Playwright error; check Modal logs
- Resource stuck in `scraping` — Modal timeout; will be recovered by Phase 8 orchestration

---

### Scrape: YouTube

```bash
modal run src.deployment.modal_workers::scrape_resource --resource-id "<uuid>"
```

Resource must have `pipeline_stage = discovered` and `type = youtube`.

**Verify**: Supabase `resources` — `pipeline_stage = scraped`, `scraped_content.metadata.type = youtube`, `scraped_content.markdown` contains transcript.

**Failures**:
- `RequestBlocked` — proxy not configured or not working; check `SCRAPING_PROXY_URL` in Modal secret `app-config-{env}`
- `TranscriptsDisabled` / `NoTranscriptFound` — video has no captions; `pipeline_stage = failed`
- `VideoUnavailable` — private or deleted video; `pipeline_stage = failed`
- `pipeline_stage = failed`, `failure_reason = "Insufficient content"` — transcript < 50 words

---

## Supabase: Common Queries

Run in Supabase dashboard → SQL Editor.

```sql
-- Resources by stage
SELECT pipeline_stage, count(*) FROM resources GROUP BY pipeline_stage;

-- Failed resources with reasons
SELECT id, url, failure_reason, updated_at
FROM resources WHERE pipeline_stage = 'failed' ORDER BY updated_at DESC;

-- Recently scraped
SELECT id, url, pipeline_stage, scraped_content->'metadata' AS meta, updated_at
FROM resources WHERE pipeline_stage = 'scraped' ORDER BY updated_at DESC LIMIT 10;
```
