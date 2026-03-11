# CMR Backend — Developer Runbook

Commands for testing individual pipeline stages. No explanations — see `_local/README.md` and `specs/` for context.

---

## Setup (one-time)

```bash
uv sync
cp .env.example .env   # fill in credentials
uv run python scripts/migrate.py
```

**Discovery table**: To enable content discovery (sitemap/RSS/YouTube), apply the discovery_sources migrations once:

```bash
psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/004_discovery_sources.sql
psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/005_discovery_first_run_at.sql
```

Or run the SQL in Supabase Dashboard → SQL Editor (contents of each file). Migration 005 adds `first_run_at` for first-run vs ongoing limits.

**Drop legacy job queue (optional):** If the DB was created with the starter `001_jobs.sql` (jobs table and PGMQ), apply `006_drop_jobs.sql` to remove them. CMR uses only the resource pipeline (discovery, scrape, ingest); no POST /jobs.

```bash
psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/006_drop_jobs.sql
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

Generic job queue (POST /jobs, recover_orphaned_jobs) has been removed; the pipeline uses only discovery, scrape, and ingest workers.

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

### Ingest to Graphiti

Resource must have `pipeline_stage = scraped` and `scraped_content` with `word_count >= INGEST_MIN_WORD_COUNT` (default 100). Neo4j and OpenAI (or equivalent) must be set in Modal secrets (`app-config-{env}`) and in `.env` for local runs.

```bash
modal run src.deployment.modal_workers::ingest_resource --resource-id "<uuid>"
```

**Verify**: Supabase `resources` — `pipeline_stage = complete`, `failure_reason` null. Knowledge graph (Neo4j via Graphiti) contains ingested content as episodes.

**Failures**:
- Resource not in `scraped` — worker logs and returns; no DB change (e.g. "Resource already claimed or not in scraped stage" if already `ingesting` or other stage).
- `pipeline_stage = failed`, `failure_reason = "Insufficient content for ingestion"` — scraped_content missing or word count below threshold.
- `pipeline_stage = failed`, other `failure_reason` — Graphiti/Neo4j/LLM error; check Modal logs.
- Resource stuck in `ingesting` — Modal timeout; recovery in Phase 8.

**Env vars** (see `.env.example`): `INGEST_MIN_WORD_COUNT`, `INGEST_STUCK_TIMEOUT_MINUTES`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `OPENAI_API_KEY`.

---

## Neo4j: Verify ingestion

After a successful ingest, the episode appears in Neo4j as `resource_<uuid>`. Run in Neo4j Browser or via MCP.

```cypher
// Episodes from this pipeline (name = resource_<resource_id>)
MATCH (e:Episodic)
WHERE e.name STARTS WITH "resource_"
RETURN e.name AS name, e.source_description AS source_description
ORDER BY e.name;

// Entities mentioned by a given resource episode (replace UUID)
MATCH (e:Episodic)-[:MENTIONS]->(ent:Entity)
WHERE e.name = "resource_24a45ed6-dd8a-450f-989d-22322edc4faf"
RETURN e.name AS episode, ent.name AS entity;

// Count entities and RELATES_TO for that episode’s mentions
MATCH (e:Episodic)-[:MENTIONS]->(ent:Entity)
WHERE e.name = "resource_<your-resource-id>"
WITH e, collect(ent) AS entities
MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
WHERE a IN entities AND b IN entities
RETURN count(DISTINCT r) AS relation_count, count(DISTINCT a) + count(DISTINCT b) AS entity_count;
```

**Cross-check**: Supabase `resources` row with same `id` should have `pipeline_stage = complete` and `failure_reason` null.

---

## Discovery: Sources and runs

Discovery reads from the `discovery_sources` table (apply migration once; see **Setup**). Only rows with `enabled = true` are used. Per-source config is in the `config` JSONB column.

**Add/update sources** (Supabase SQL Editor or psql):

```sql
-- Sitemap
INSERT INTO discovery_sources (id, source_type, name, config, enabled)
VALUES (
  gen_random_uuid(),
  'sitemap',
  'My sitemap',
  '{"url": "https://example.com/sitemap.xml", "days_back": 7, "require_https": true}'::jsonb,
  true
);

-- RSS
INSERT INTO discovery_sources (id, source_type, name, config, enabled)
VALUES (
  gen_random_uuid(),
  'rss',
  'My RSS',
  '{"feed_url": "https://example.com/feed.xml", "days_back": 14}'::jsonb,
  true
);

-- YouTube (requires YOUTUBE_API_KEY in Modal secret / .env)
INSERT INTO discovery_sources (id, source_type, name, config, enabled)
VALUES (
  gen_random_uuid(),
  'youtube_channel',
  'My channel',
  '{"channel_id": "UCxxxxxx", "max_videos": 20}'::jsonb,
  true
);
```

**Enable/disable**: `UPDATE discovery_sources SET enabled = false WHERE id = '<uuid>';` (or `true` to enable).

**Run discovery** (dry-run first, then live):

```bash
modal run src.deployment.modal_workers::run_discovery --dry-run
modal run src.deployment.modal_workers::run_discovery
```

**Verify**: New rows in `resources` with `pipeline_stage = discovered`, `discovery_source_id` set. Scrape jobs spawned for each new resource. Re-run discovery with same sources → no duplicate URLs (idempotent).

**Troubleshooting**: No sources run → check `enabled = true` and `source_type` in `sitemap`, `rss`, `youtube_channel`. YouTube errors → set `YOUTUBE_API_KEY` in Modal secret `app-config-{env}` (and in `.env` for local). One failing source does not stop others; check logs for which source failed.

**First run vs ongoing**: The first time a source is included in a non–dry_run discovery run, discovery uses tight initial limits so only the most recent items are pulled. After that run, the source is marked and subsequent runs use the normal config (`days_back`, `max_videos`, etc.). You can tune first-run behavior via optional `initial_days_back`, `initial_max_urls` (sitemap), or `initial_max_videos` (YouTube) in the source `config`, or via env: `DISCOVERY_INITIAL_DAYS_BACK`, `DISCOVERY_INITIAL_MAX_URLS`, `DISCOVERY_INITIAL_MAX_VIDEOS`. To re-onboard a source (treat as first run again), set `first_run_at = NULL` for that row. Requires migration `docs/db/migrations/005_discovery_first_run_at.sql` (adds `first_run_at` column).

Full flow (migration → sources → dry-run → live → idempotency): see `specs/006-content-discovery/quickstart.md`.

---

## Re-queue failed resource

Reset a failed resource to `discovered` so it re-enters the pipeline (will be scraped again, then ingested).

**SQL (Supabase SQL Editor or psql):**

```sql
UPDATE resources
SET pipeline_stage = 'discovered', failure_reason = NULL
WHERE id = '<uuid>';
```

**Re-trigger scrape** (then ingest will spawn automatically after scrape):

```bash
modal run src.deployment.modal_workers::scrape_resource --resource-id "<uuid>"
```

**Alternative — API**: `POST /api/v1/resources/<resource_id>/requeue` with `Authorization: Bearer $JWT_TOKEN`; returns 200 with updated resource or 404.

---

## Resource-pipeline recovery

A scheduled Modal function runs **every 15 minutes** and marks resources stuck in `scraping` or `ingesting` (older than `SCRAPE_STUCK_TIMEOUT_MINUTES` or `INGEST_STUCK_TIMEOUT_MINUTES`) as `failed` with a clear reason (`Stuck scraping timeout` / `Stuck ingesting timeout`).

**Run recovery manually:**

```bash
modal run src.deployment.modal_workers::run_recovery_pipeline
```

**Verify stuck → failed:** In Supabase, before recovery: resources in `scraping` or `ingesting` with `updated_at` older than the timeout. After recovery: those rows have `pipeline_stage = 'failed'` and `failure_reason` set. Query:

```sql
SELECT id, url, pipeline_stage, failure_reason, updated_at
FROM resources
WHERE pipeline_stage IN ('scraping', 'ingesting', 'failed')
ORDER BY updated_at DESC;
```

---

## Full-pipeline test

1. Add a discovery source (see **Discovery: Sources and runs**); ensure at least one source has `enabled = true`.
2. Run discovery: `modal run src.deployment.modal_workers::run_discovery --dry-run` then `modal run src.deployment.modal_workers::run_discovery`.
3. Confirm in Supabase: new resources with `pipeline_stage = discovered`; scrape spawns automatically; after scrape, ingest spawns automatically.
4. Confirm resources move: `discovered` → `scraping` → `scraped` → `ingesting` → `complete` (or `failed`). Check Neo4j for completed resources.

Step-by-step: `specs/001-pipeline-orchestration-recovery/quickstart.md`.

---

## Manual triggers

Use these to run pipeline stages on demand (debug, backfill, or after re-queue). Full flow: see `specs/001-pipeline-orchestration-recovery/quickstart.md`.

| Action | Command |
|--------|---------|
| Discovery (dry-run) | `modal run src.deployment.modal_workers::run_discovery --dry-run` |
| Discovery (live) | `modal run src.deployment.modal_workers::run_discovery` |
| Scrape one resource | `modal run src.deployment.modal_workers::scrape_resource --resource-id "<uuid>"` |
| Ingest one resource | `modal run src.deployment.modal_workers::ingest_resource --resource-id "<uuid>"` |

After a successful scrape, ingest is spawned automatically; you only need to run `ingest_resource` manually for a single resource (e.g. re-ingest) or if scrape was run standalone.

---

## Supabase: Common Queries

Run in Supabase dashboard → SQL Editor.

```sql
-- Resources by stage
SELECT pipeline_stage, count(*) FROM resources GROUP BY pipeline_stage;

-- Failed resources with reasons
SELECT id, url, failure_reason, updated_at
FROM resources WHERE pipeline_stage = 'failed' ORDER BY updated_at DESC;

-- Recently scraped (ready for ingestion)
SELECT id, url, pipeline_stage, scraped_content->'metadata' AS meta, updated_at
FROM resources WHERE pipeline_stage = 'scraped' ORDER BY updated_at DESC LIMIT 10;

-- Recently ingested (complete)
SELECT id, url, pipeline_stage, failure_reason, updated_at
FROM resources WHERE pipeline_stage = 'complete' ORDER BY updated_at DESC LIMIT 10;
```
