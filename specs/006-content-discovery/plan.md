# Implementation Plan: Phase 5 — Content Discovery (Sitemap, RSS, YouTube)

**Branch**: `006-content-discovery` | **Date**: 2025-03-08 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/006-content-discovery/spec.md`

## Summary

Implement content discovery that reads configured sources (sitemap, RSS, YouTube channel) from a new `discovery_sources` table, filters and deduplicates URLs, submits net-new URLs to the existing batch create path, and triggers scraping only for resources created in that run. Created resources store provenance via optional `discovery_source_id` (extend `insert_resource` and `batch_create` to accept it; discovery passes it when calling batch create, e.g. per-source batches). Discovery runs as a scheduled Modal function (e.g. daily) and supports dry-run. Per-source failures do not abort the run. Stack: Python 3.11, FastAPI (existing API), Supabase (new table + existing resources), Modal (new scheduled function + existing scrape spawn).

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, Supabase (client + asyncpg where needed), Modal, httpx, feedparser (RSS), sitemap parsing (stdlib XML or small lib), YouTube Data API or equivalent for channel videos  
**Storage**: PostgreSQL (Supabase): new `discovery_sources` table; existing `resources` table (with optional `discovery_source_id` already present)  
**Testing**: pytest for service/DAO logic; runbook-driven manual verification for scheduled discovery and dry-run  
**Target Platform**: Modal (scheduled discovery function); local dev via existing scripts  
**Project Type**: Web service (API) + scheduled background workers  
**Performance Goals**: Discovery run completes within a reasonable timeout (e.g. 10–15 min) for tens of sources; batch submit and batch spawn avoid per-URL blocking  
**Constraints**: Discovery authenticates to API using service-account JWT (Modal secret); no new public API endpoints; RSS auto-discovery out of scope  
**Scale/Scope**: Tens of discovery sources; hundreds to low thousands of candidate URLs per run; deduplication and net-new-only submit/scrape

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Quick Start**: No new setup steps that block the 10-minute path; optional env (e.g. YouTube API key) documented in runbook and `.env.example`. New table created via migration script.
- **REST API**: No new REST endpoints; discovery calls existing `POST /api/v1/resources`. Health and docs unchanged.
- **Cloud-Ready**: Discovery worker is stateless; config in Supabase table; deployment via existing Modal deploy; schedule configurable (e.g. `modal.Period(days=1)`).
- **Observability**: Use existing `get_logger(__name__)` and structured logging in discovery service; log source-level success/failure and counts; no new request-ID (scheduled job, not HTTP).
- **Developer Guidance**: Follow `_local/starter-kit/patterns.md` (Service → DAO), `_local/starter-kit/modal-jobs.md` (scheduled function pattern like `recover_orphaned_jobs`), `_local/starter-kit/data-layer.md` (migrations in `docs/db/migrations/`).

**Result**: Pass — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/006-content-discovery/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0: sitemap/RSS/YouTube choices, filter defaults
├── data-model.md        # Phase 1: discovery_sources entity, fields, validation
├── quickstart.md        # Phase 1: run discovery locally / dry-run / verify table
├── contracts/           # Phase 1: discovery run invocation (schedule, dry-run)
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit.tasks — not created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── api/                     # No new routes; discovery calls existing POST /resources
├── deployment/
│   └── modal_workers.py      # Add run_discovery(schedule=Period(days=1)); optional dry_run param
├── models/
│   └── config.py             # Optional: DISCOVERY_DAYS_BACK_DEFAULT, DISCOVERY_BATCH_SIZE, etc.
├── services/
│   ├── discovery/           # NEW: discovery domain
│   │   ├── __init__.py
│   │   ├── service.py       # run_discovery(dry_run): load sources → sitemap/rss/youtube scanners → filter → dedupe → batch create → batch spawn scrape
│   │   ├── sitemap_scanner.py
│   │   ├── rss_scanner.py
│   │   └── youtube_scanner.py
│   ├── supabase/
│   │   ├── discovery_sources_dao.py   # NEW: list enabled sources, get by id
│   │   └── resources_dao.py            # Existing; extend insert_resource with optional discovery_source_id; optional get_existing_urls(urls) for dedupe
│   └── resources_service.py           # Existing batch_create; extend with optional discovery_source_id; discovery calls it directly (internal)
docs/
├── db/
│   └── migrations/
│       └── 004_discovery_sources.sql  # NEW: discovery_sources table
└── runbook.md               # Add: discovery table, run discovery (dry-run + live), verify
tests/
```

**Structure Decision**: Single backend; new `services/discovery` with service + three scanner modules; new DAO `discovery_sources_dao`; new migration for `discovery_sources`; one new Modal scheduled function `run_discovery`. Discovery may call `batch_create` and scrape spawner directly from the worker (same process as API) to avoid HTTP round-trip and reuse auth from Modal secrets.

## Complexity Tracking

No constitution violations; table left empty.

## Phase 0: Research

See [research.md](./research.md). Resolved: sitemap parsing approach, RSS library, YouTube channel video listing, filter defaults, and how discovery invokes resource creation and scrape (internal call vs HTTP).

## Phase 1: Design

- **Data model**: [data-model.md](./data-model.md) — `discovery_sources` table, source types, filter fields, enabled flag.
- **Contracts**: [contracts/](./contracts/) — discovery run invocation (scheduled vs manual, dry_run).
- **Quickstart**: [quickstart.md](./quickstart.md) — apply migration, add sources, run discovery (dry-run then live), verify resources and scrape.

## Post–Phase 1 Constitution Re-check

- Quick Start: Migration and runbook steps are additive; 10-minute path unchanged. **Pass**
- REST API: No new endpoints. **Pass**
- Cloud-Ready: Stateless worker; config in DB. **Pass**
- Observability: Logging in discovery service. **Pass**
- Developer Guidance: Patterns and runbook updated. **Pass**

**Result**: Pass.
