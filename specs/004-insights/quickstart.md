# Quickstart: Phase 3 — Insights (AI Extraction)

**Target**: Developer runs the insight extraction worker via Modal after completing Phase 2 (Scraping) setup.

---

## Prerequisites

Same as Phase 2, plus:

- **Phase 2 complete**: At least one resource with `pipeline_stage = scraped` and `scraped_content` populated
- **Modal account** — required for insight worker (not optional)
- **Modal secrets**: `supabase-credentials-{ENV}`, `app-config-{ENV}` — same as existing workers; no additional secret needed
- **Model config**: `MODEL_INSIGHT_EXTRACTION` and `OPENROUTER_API_KEY` go in `.env` and are pushed to `app-config-{ENV}` automatically by `deploy.py`

**Optional env vars**:
- `INSIGHT_MIN_WORD_COUNT` (default 100) — minimum word count for insight extraction; below this, mark `failed` with "Insufficient content for insight extraction"
- `INSIGHT_STUCK_TIMEOUT_MINUTES` (default 30) — used by recovery worker (Phase 8) to reset stuck `extracting` resources; set above the 10-min function timeout to avoid false positives

---

## Setup

### 1. Install dependencies

```bash
uv add "pydantic-ai==1.0.5" openai
```

(Or add to `pyproject.toml` and run `uv sync`.) Pin to `1.0.5` — the v1.x API differs from earlier versions (`output_type=` not `result_type=`; `result.output` not `result.data`; `instructions=` not `system_prompt=` in constructor).

### 2. Configure model

Add `MODEL_INSIGHT_EXTRACTION` and `OPENROUTER_API_KEY` to `.env`. They will be pushed to `app-config-{ENV}` automatically when you run `deploy.py`.

```bash
# .env
MODEL_INSIGHT_EXTRACTION=x-ai/grok-4-fast
OPENROUTER_API_KEY=sk-or-...
```

### 3. Deploy workers

```bash
uv run deploy_dev
```

This deploys the Modal app including `extract_insights`.

### 4. Create a test resource (if needed)

```bash
# Get JWT
export JWT_TOKEN=$(uv run python scripts/get_jwt.py)

# Create resource
curl -X POST http://localhost:8000/api/v1/resources \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/article"]}'

# Run scrape worker first (Phase 2)
modal run src.deployment.modal_workers::scrape_resource --resource-id "<resource-uuid>"
```

Note the `resource_id` after scrape completes (`pipeline_stage = scraped`).

---

## Run Insight Extraction Worker

### Via Modal CLI

```bash
modal run src.deployment.modal_workers::extract_insights --resource-id "<resource-uuid>"
```

Replace `<resource-uuid>` with a resource in `scraped` stage.

### Via Modal Dashboard

1. Open Modal dashboard
2. Find the `Job-Worker-{ENV}` app
3. Select `extract_insights` function
4. Enter `resource_id` as argument
5. Run

---

## Verify

| Action | How |
|--------|-----|
| Check resource in Supabase | Query `resources` where `id = <resource_id>`; confirm `pipeline_stage = extracted`, `insight` populated |
| Check insight structure | Inspect `insight` JSONB; confirm `resource_overview`, `resource_insights`, `entities`, `relationships` |
| Check no alignment | Confirm `insight` does NOT contain `alignment` field |
| Check failure handling | Use a resource with very short content; confirm `pipeline_stage = failed`, `failure_reason` populated |

---

## Test Checklist (from build-plan)

- [ ] Spawn insight worker with `resource_id` (resource in `scraped`); confirm `scraped` → `extracting` → `extracted`
- [ ] Confirm `insight` JSONB populated on resource row
- [ ] Inspect insight structure — confirm no `alignment` field
- [ ] Spawn against resource with very short scraped content — confirm `pipeline_stage = failed`, `failure_reason` populated
- [ ] Spawn against resource already `extracted` — confirm skip or graceful failure

---

## Troubleshooting

- **Modal timeout**: 5 min default; long content may take longer. Resource may stay `extracting` until recovery (Phase 8).
- **MODEL_INSIGHT_EXTRACTION not set**: Ensure env var is in Modal secrets. Check `llm-credentials-{ENV}` or `app-config-{ENV}`.
- **LLM rate limit**: Modal retries=1 may help; check provider limits.
- **Resource not found**: Ensure `resource_id` is a valid UUID and exists in `resources` table.
- **"Insufficient content"**: `scraped_content` has word_count < INSIGHT_MIN_WORD_COUNT. Use a resource with more content.
- **Not eligible** (stage != scraped): Resource must be in `scraped` stage. Run scrape worker first.
