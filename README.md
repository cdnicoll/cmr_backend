# CMR Backend

FastAPI backend with Modal workers and Supabase. Content pipeline: discovery (sitemap/RSS/YouTube) → scrape → ingest (Graphiti/Neo4j).

## Overview

This project provides:

- **REST API** — FastAPI with health checks, JWT auth, and resources API (batch create URLs)
- **Resource pipeline** — Discovery runs on a schedule; new URLs become resources; scrape and ingest workers process them. Three Modal workers: run_discovery, scrape_resource, ingest_resource.
- **No generic job queue** — CMR does not use POST /jobs or a jobs table; the pipeline is driven by discovery and spawns (scrape → ingest).

## Prerequisites

- **Python 3.11+**
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Supabase project** — URL, publishable key, secret key, transaction pooler URL
- **Modal account** (for deployment; optional for local-only)

## Getting Started

### 1. Clone and install

```bash
git clone <repo-url>
cd cmr-backend_v2
uv sync
```

### 2. Environment

```bash
cp .env.example .env
# Edit .env with your Supabase and Modal credentials
```

Required variables: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `TRANSACTION_POOLER_URL`. Optional: `ENVIRONMENT`, `MODAL_PROJECT`.

### 3. Database migration

Apply migrations for resources and discovery. See `docs/runbook.md` for exact steps (e.g. `psql "$TRANSACTION_POOLER_URL" -f docs/db/migrations/002_resources.sql`, then 004 and 005 for discovery). If the DB had the starter jobs table, apply `006_drop_jobs.sql` to remove it and PGMQ.

### 4. Run locally

```bash
uv run python scripts/dev.py
```

API: **http://localhost:8000** · Docs: **http://localhost:8000/docs**

### Verify

| Action        | Command / URL                                       |
|---------------|-----------------------------------------------------|
| Health        | `curl http://localhost:8000/health`                 |
| DB health     | `curl http://localhost:8000/health/db`              |
| Create resources | `POST /api/v1/resources` with `Authorization: Bearer <JWT>` and `{"urls":["https://example.com"]}` |

## Project Structure

```
src/
├── api/              # FastAPI app, routes, dependencies
├── config/           # Supabase, database connection
├── deployment/       # Modal app, workers (discovery, scrape, ingest), deploy script
├── middleware/      # CORS, metrics, request ID
├── models/          # Config, resources, responses
├── services/        # Discovery, scraping, ingestion, supabase DAOs
└── utils/            # Logging
scripts/              # dev.py, create_modal_secrets.sh
docs/                 # runbook.md, db/migrations
```

## Deploy to Modal

```bash
uv run deploy_dev   # or deploy_prod
```

Before first deploy, create Modal secrets:

```bash
source .env
./scripts/create_modal_secrets.sh   # prints exact commands
# Run the printed modal secret create commands
```

## Documentation

- **[docs/quickstart.md](docs/quickstart.md)** — Detailed setup and troubleshooting
- **[docs/conventions.md](docs/conventions.md)** — Patterns for adding routes, services, job types

## License

See repository.
