# CMR Backend — Application Overview

**CMR (Content Mining & Research)** is a backend for mining-industry content intelligence. It discovers URLs from configured sources, scrapes and ingests them into a Neo4j knowledge graph via Graphiti, and exposes the graph for downstream use (e.g. LLM clients via Neo4j MCP). This document describes what the application does, its data model, and where to find operational and historical detail.

---

## What the application does

1. **Discovery** — A scheduled Modal function (`run_discovery`) reads the `discovery_sources` table (sitemaps, RSS feeds, YouTube channels), finds new URLs, deduplicates against existing resources, and creates new rows in `resources` with `pipeline_stage = discovered`. It then spawns a scrape job for each new resource.
2. **Scraping** — The `scrape_resource` Modal function fetches content (Crawl4AI for websites, youtube-transcript-api for YouTube), stores it in `scraped_content` on the resource, and sets `pipeline_stage` to `scraped` or `failed`. On success it spawns the ingest worker for that resource.
3. **Ingestion** — The `ingest_resource` Modal function reads `scraped_content`, validates (e.g. min word count), sends text to Graphiti, and updates `pipeline_stage` to `complete` or `failed`. Graphiti performs LLM extraction, entity merge, and writes to Neo4j.
4. **Recovery** — A scheduled Modal function (`run_recovery_pipeline`) runs on an interval (e.g. every 2 hours). It finds resources stuck in `scraping` or `ingesting` (older than `SCRAPE_STUCK_TIMEOUT_MINUTES` or `INGEST_STUCK_TIMEOUT_MINUTES`) and marks them `failed` with a clear reason.
5. **Re-queue** — Operators can reset a failed resource to `discovered` (via runbook SQL or `POST /api/v1/resources/<id>/requeue`) and re-trigger scrape (and thus ingest) manually.

**Pipeline flow:** Discovery → scrape (spawned per new resource) → ingest (spawned after successful scrape) → `complete` or `failed`. Recovery cleans up stuck resources; re-queue allows manual retry.

Trend analysis and content generation are **out of scope** for this backend; they are handled by an LLM client connected directly to Neo4j (e.g. via MCP).

---

## Terminology

| Term | Definition |
|------|------------|
| **discovery_source** | A monitored source (sitemap, RSS, or YouTube channel) stored in Supabase. Discovery scans these for new URLs. |
| **resource** | A single content item (web URL or YouTube video URL). Has a `pipeline_stage` and optional `scraped_content` and `failure_reason`. |
| **pipeline_stage** | `discovered` → `scraping` → `scraped` → `ingesting` → `complete` or `failed`. |
| **discovery** | The process that scans discovery_sources, creates resources for new URLs, and spawns scrape for each. |

---

## Data model

**Supabase (PostgreSQL)**

| Table | Purpose |
|-------|---------|
| `discovery_sources` | Sources to monitor: `source_type` = `sitemap`, `rss`, or `youtube_channel`; config (URLs, limits) in JSONB. |
| `resources` | Content units: `url`, `type` (website/youtube), `pipeline_stage`, `scraped_content` (JSONB), `failure_reason`, `discovery_source_id`. |

**Neo4j** — Knowledge graph populated by Graphiti during ingestion. Entities, relationships, and episodic data. Queried by downstream LLM clients (e.g. via MCP).

---

## Stack and workers

- **API:** FastAPI, Supabase JWT auth, asyncpg for DB.
- **Workers (Modal):** `run_discovery` (scheduled), `scrape_resource` (spawned), `ingest_resource` (spawned), `run_recovery_pipeline` (scheduled).
- **Scraping:** Crawl4AI (websites) and youtube-transcript-api (YouTube); optional proxy via `SCRAPING_PROXY_URL`.
- **Graph:** Graphiti + Neo4j; env vars in Modal app-config secret.

Config is in `src/models/config.py` and `.env`; deploy pushes secrets from `.env` to Modal via `src/deployment/deploy.py` before `modal deploy`.

---

## Deploy and secrets

- **Deploy:** `uv run deploy_dev` or `uv run deploy_prod`. This loads `.env`, runs `push_modal_secrets()` (which runs `modal secret create --force` for `supabase-credentials-{env}` and `app-config-{env}`), then deploys `modal_app.py` and `modal_workers.py`.
- **New env vars:** Add to `.env`, `.env.example`, and `push_modal_secrets()` in `src/deployment/deploy.py` so workers get them.
- **Manual secrets only:** Use `scripts/create_modal_secrets.sh` (source `.env` first; it prints the `modal secret create` commands).

---

## Key decisions (reference)

| Area | Decision |
|------|----------|
| Auth | Supabase JWT only; no API keys. Modal uses a service-account JWT in secrets. |
| Pipeline state | Single `pipeline_stage` column. Graphiti is the only extractor; no separate “insights” step. |
| Failed retry | Manual re-queue only (runbook or API). No automatic retries. |
| Jobs table | Removed. No POST /jobs or job queue; pipeline is resource-based only. |
| Trends / content gen | Not in backend; LLM client uses Neo4j MCP. |

---

## Where to find things

| Need | Location |
|------|----------|
| **Commands (run pipeline, deploy, re-queue, recovery)** | `docs/runbook.md` |
| **Cost (Modal workers)** | `docs/modal-cost-forecast.md` |
| **Phase-by-phase build history and test criteria** | `_local/build-plan.md` |
| **Per-phase specs and tasks** | `specs/` (e.g. `specs/001-pipeline-orchestration-recovery/`) |

**Codebase:** Routes in `src/api/routes/`; services in `src/services/`; DAOs in `src/services/supabase/`. Modal workers in `src/deployment/modal_workers.py`. Config in `src/models/config.py`.
