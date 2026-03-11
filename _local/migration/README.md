# CMR Backend — High-Level Overview & Setup

**CMR (Content Mining & Research)** is a backend for mining-industry content intelligence. It discovers URLs from configured sources (sitemaps, RSS, YouTube), scrapes and ingests them into a Neo4j knowledge graph via Graphiti, and exposes the graph for downstream use (e.g. LLM clients via Neo4j MCP).

**Pipeline:** Discovery (scheduled) → scrape (per new resource) → ingest (after successful scrape) → `complete` or `failed`. A recovery job marks stuck resources as failed; operators can re-queue failed resources manually. Trends and content generation are handled outside this backend (e.g. LLM + Neo4j MCP).

**Stack:** FastAPI, Supabase (PostgreSQL + JWT auth), Modal (discovery, scrape, ingest, recovery workers), Crawl4AI + youtube-transcript-api for scraping, Graphiti + Neo4j for the knowledge graph.

---

## Runbook — Commands & Operations

All day-to-day commands (deploy, run pipeline stages, re-queue, recovery, verification queries) are in the **developer runbook**:

→ **[docs/runbook.md](../../docs/runbook.md)**

Use it for: setup, JWT, deploy, running discovery/scrape/ingest, re-queue, recovery, and Supabase queries.

---

## Setup (one-time)

From the repo root:

1. **Install and env**
   ```bash
   uv sync
   cp .env.example .env   # fill in Supabase, DB, Neo4j, OpenAI, Modal, etc.
   ```

2. **Database**
   ```bash
   uv run python scripts/migrate.py
   ```

3. **Discovery (optional)** — To use sitemap/RSS/YouTube discovery, apply:
   ```bash
   psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/004_discovery_sources.sql
   psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/005_discovery_first_run_at.sql
   ```
   Or run the SQL in Supabase Dashboard → SQL Editor.

4. **Drop legacy job queue (optional)** — If the DB had the starter jobs table:
   ```bash
   psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/006_drop_jobs.sql
   ```

5. **JWT for API** — For local API calls:
   ```bash
   eval $(uv run python scripts/get_jwt.py | grep "^export")
   ```

6. **Deploy to Modal**
   ```bash
   uv run deploy_dev    # or deploy_prod
   ```

Full setup details, failure handling, and verification steps: **[docs/runbook.md](../../docs/runbook.md)**.
