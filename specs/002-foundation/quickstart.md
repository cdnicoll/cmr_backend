# Quickstart: Phase 1 — Foundation (Resources and Auth)

**Target**: Developer runs API with Resources endpoint after completing starter setup.

---

## Prerequisites

Same as starter (001-starter-application):

- **Python 3.11+**
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Supabase project** — URL, publishable key, secret key, transaction pooler URL
- **Modal account** (optional for local-only)

---

## Setup

### 1. Clone and install (if not already done)

```bash
git clone <repo-url>
cd cmr-backend_v2
uv sync
```

### 2. Environment

Copy `.env.example` to `.env` and configure (same as starter). No new env vars for Phase 1.

### 3. Database migration

```bash
uv run python scripts/migrate.py
```

Creates: `jobs` table, PGMQ `job_queue` (starter), **plus** `resources` table (Phase 1).

### 4. Run API locally

```bash
uv run python scripts/dev.py
```

API: `http://localhost:8000`

---

## Verify

| Action | Command / URL |
|--------|---------------|
| Health | `curl http://localhost:8000/health` |
| DB health | `curl http://localhost:8000/health/db` |
| API docs | Open `http://localhost:8000/docs` |
| Create resources | See below |

### Create resources (requires JWT)

```bash
# Replace <JWT> with a valid Supabase Auth token
curl -X POST http://localhost:8000/api/v1/resources \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/article-1", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]}'
```

**Expected**: `201 Created` with `created`, `skipped`, `errors`, and `results` array.

### Verify in Supabase

Query `resources` table — new rows should have `pipeline_stage = discovered`, `type = website` or `youtube`.

### Auth check

```bash
# No JWT — expect 401
curl -X POST http://localhost:8000/api/v1/resources \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/test"]}'
```

**Expected**: `401 Unauthorized`

---

## Test Checklist (from build-plan)

- [ ] `GET /health` and `GET /health/db` return 200
- [ ] `POST /api/v1/resources` with valid URL returns 201; resource in Supabase with `pipeline_stage = discovered`
- [ ] `POST /api/v1/resources` with same URL again returns 200 (skipped)
- [ ] `POST /api/v1/resources` with invalid or SSRF URL returns 422
- [ ] `POST /api/v1/resources` with YouTube URL creates resource with `type = youtube`
- [ ] Query Supabase: `resources` table schema matches spec (`pipeline_stage`, `failure_reason`, `scraped_content`, `insight`, `discovery_source_id`)
- [ ] Protected endpoint without JWT returns 401

---

## Deploy (Modal)

Same as starter. Phase 1 adds no new deployment steps. Resources API is part of the existing API deployment.

```bash
uv run deploy_dev   # or deploy_prod
```

---

## Troubleshooting

- **401 on resources**: Use valid Supabase Auth JWT. For programmatic/cron callers, use service account JWT in Modal secrets.
- **422 on URL**: Check URL format; SSRF blocks internal IPs. Ensure URL is https and well-formed.
- **Migration fails**: Ensure `resources` table migration is included in `scripts/migrate.py` or run `002_resources.sql` manually.
