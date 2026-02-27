# Data Model: Phase 1 — Foundation (Resources and Auth)

**Feature**: 002-foundation  
**Date**: 2025-02-27 | **Phase**: 1

## Entities

### 1. Resource

URL lifecycle record stored in `public.resources`. Entry point for all content into the pipeline.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| id | UUID | No | Primary key (default gen_random_uuid()) |
| url | TEXT | No | Canonical URL (unique) |
| title | TEXT | Yes | Optional; populated later by scraping |
| type | TEXT | No | `website` or `youtube` |
| pipeline_stage | TEXT | No | Lifecycle stage (see below) |
| failure_reason | TEXT | Yes | Error message when stage = failed |
| scraped_content | JSONB | Yes | Raw scraped content; NULL in Phase 1, populated in Phase 2 |
| insight | JSONB | Yes | Extracted entities/relationships; NULL in Phase 1, populated in Phase 3 |
| discovery_source_id | UUID | Yes | FK to discovery_sources (no constraint in Phase 1); NULL for manually submitted resources, populated by discovery worker in Phase 5 |
| created_at | TIMESTAMPTZ | No | Insert time |
| updated_at | TIMESTAMPTZ | No | Last update |

**Indexes**:
- `resources_url_key` — UNIQUE on `(url)`
- `resources_pipeline_stage_idx` on `(pipeline_stage)` — for downstream workers
- `resources_created_at_idx` on `(created_at)` — for listing/ordering

**Pipeline stage values** (enum or check constraint):
- `discovered` — Initial state; eligible for scraping
- `scraping` — Scrape in progress (Phase 2)
- `scraped` — Content extracted (Phase 2)
- `extracting` — Insight extraction in progress (Phase 3)
- `extracted` — Insights stored (Phase 3)
- `ingesting` — Graphiti ingestion in progress (Phase 4)
- `complete` — Fully processed (Phase 4)
- `failed` — Error at any stage; `failure_reason` populated

**State transitions** (Phase 1 creates only `discovered`):
- Insert → `discovered`
- (Phase 2+) `discovered` → `scraping` → `scraped`
- (Phase 3+) `scraped` → `extracting` → `extracted`
- (Phase 4+) `extracted` → `ingesting` → `complete`
- Any → `failed` (on error)

**Phase 1 scope**: `scraped_content` and `insight` are present but NULL; no code reads or writes them until Phase 2/3. `discovery_source_id` is NULL for manually submitted resources until Phase 5.

---

### 2. Authentication (no new tables)

Auth uses starter kit's Supabase Auth (JWT). No `api_keys` table. No new auth entities in Phase 1.

---

## Validation Rules

### Resource

- `url` MUST be unique
- `type` MUST be `website` or `youtube`
- `pipeline_stage` MUST be one of the defined values
- `url` MUST pass SSRF validation before insert
- `url` MUST be normalized (scheme, trailing slash) before uniqueness check

### URL Validation (pre-insert)

- Block: localhost, 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, link-local, etc.
- Normalize: https preferred; remove trailing slash for consistency (or standardize)
- Type detection: YouTube patterns → `youtube`; else `website`

---

## Migration Script

**Location**: `docs/db/migrations/002_resources.sql` or extend `scripts/migrate.py`

**Idempotent operations**:
- `CREATE TABLE IF NOT EXISTS resources (...)` with columns above (including `scraped_content` JSONB, `insight` JSONB, `discovery_source_id` UUID — all nullable)
- `CREATE UNIQUE INDEX IF NOT EXISTS resources_url_key ON resources(url)`
- `CREATE INDEX IF NOT EXISTS resources_pipeline_stage_idx ON resources(pipeline_stage)`
- `CREATE INDEX IF NOT EXISTS resources_created_at_idx ON resources(created_at)`
- Optional: `CHECK (pipeline_stage IN ('discovered', 'scraping', 'scraped', 'extracting', 'extracted', 'ingesting', 'complete', 'failed'))`
- Optional: `CHECK (type IN ('website', 'youtube'))`
- **updated_at trigger**: Create if not exists — `update_updated_at_column()` function (shared) + `resources_updated_at` trigger on `resources`:

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS resources_updated_at ON resources;
CREATE TRIGGER resources_updated_at
BEFORE UPDATE ON resources
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## API Schemas (Pydantic)

### BatchCreateResourceRequest
```python
urls: list[str]  # 1..N URLs
```

### BatchCreateResourceResponse
```python
created: int
skipped: int
errors: int
results: list[ResourceResult]
```

### ResourceResult
```python
url: str
status: Literal["created", "skipped", "error"]
resource_id: UUID | None  # Present when created or skipped
error: str | None         # Present when status=error
```
