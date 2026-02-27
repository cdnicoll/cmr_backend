# CMR Rebuild — Phased Build Plan

## Overview

This plan describes how to rebuild the **CMR (Content Mining & Research)** backend — a mining industry content intelligence platform — using the modern starter kit. The legacy app discovers URLs from mining sources, scrapes content via Apify, extracts entities and insights with AI, ingests them into a Neo4j knowledge graph via Graphiti, and exposes trend analysis and AI-generated content APIs. The rebuild will migrate to Supabase, Modal, and Crawl4AI while unifying the pipeline state and replacing implicit cron orchestration with an explicit, event-driven workflow.

---

## What Exists in the Starter

The starter kit already provides:

| Component | Status |
|-----------|--------|
| **FastAPI app** | Entry point, lifespan, middleware (CORS, metrics, rate limit, request ID) |
| **Supabase** | Client factory, PostgREST, RLS |
| **Transaction pooler** | asyncpg/SQLAlchemy for jobs, PGMQ |
| **Auth** | JWT verification via Supabase JWKS, `get_current_user`, `get_validated_jwt_user` |
| **Jobs** | `jobs` table, `JobQueueService`, PGMQ backup, Modal spawner |
| **Modal** | API deployment, worker tiers (GPU, browser, LLM, API), recovery worker |
| **Health** | `/health`, `/health/db` |
| **Patterns** | Service → DAO, `POST /jobs`, `GET /jobs`, `GET /jobs/{id}` |
| **Recovery** | `recover_orphaned_jobs` (scheduled every 15 min) |
| **Migration** | Script pattern, PGMQ setup |

**Not present and must be built:** Resources domain, scraping (Crawl4AI), insights agent, Graphiti/Neo4j integration, trends multi-agent, content generation, content discovery, CMR-specific auth (API keys if needed), and the resource pipeline orchestration.

---

## Stack Changes to Keep in Mind

| Concern | Legacy | New Stack | Impact |
|---------|--------|-----------|--------|
| **Database** | Neon (PostgreSQL) | Supabase (PostgreSQL) | Same SQL; use Supabase client + asyncpg pooler. RLS may apply for user-scoped data. |
| **Scraping** | Apify (external jobs, poll for `data_id`) | Crawl4AI (direct, in-process) | No `jobs` table for Apify; no status polling cron. Scraping becomes a Modal function that returns content directly. |
| **Task queue** | Celery + Redis | Modal | Replace Celery tasks with Modal functions. No `asyncio.run()` in sync tasks — Modal is async-native. |
| **Auth** | Bearer API keys (DB-stored) | Supabase Auth (JWT) | Starter uses JWT. All callers including cron and scheduled Modal functions authenticate using a dedicated service account JWT stored as a Modal secret. No changes needed to the starter's existing auth implementation. |
| **Pipeline orchestration** | 5 independent cron jobs | Modal scheduled + chained calls | Discovery runs on schedule; scrape → insight → ingest chain directly. No implicit ordering. |
| **Resource state** | `insight_status` + `graphiti_status` (dual columns) | Single `pipeline_stage` | Unified lifecycle: discovered → scraping → scraped → extracting → extracted → ingesting → complete / failed. |
| **Observability** | Logfire | Sentry (per desired-changes) | Swap logging/error reporting. |
| **Graph** | Neo4j + Graphiti | Same | No change. |
| **AI** | PydanticAI, OpenAI | Same | No change; add env vars for model swapping. |

---

## Phases

### Phase 1: Foundation — Resources and Auth

**What is being built**

- Resources table and batch creation API (`POST /api/v1/resources`)
- URL validation (SSRF protection, normalization, type detection: website vs YouTube)
- Duplicate handling (unique on `url`; skip, don't error)
- Auth: starter JWT with service account for programmatic/cron callers
- Database migration for `resource` table

**Why at this point**

Resources is the entry point for all content. Every downstream domain (scraping, insights, graph, trends, content) depends on it. Auth must be in place before protected routes.

**Domains included**

- Resources (core)
- Authentication (adapt or extend)

**Complexity**

Medium. URL validation and batch semantics are well-documented.

**Open questions / decisions**

1. ~~**Auth model:** Legacy uses API keys for cron and external callers. Starter uses JWT. Options: (a) JWT only — use service account for cron; (b) Add API key table and `validate_api_key` dependency alongside JWT; (c) JWT for UI, API keys for programmatic. Recommend (b) or (c) if cron jobs must call the API with a key.~~ **RESOLVED:** Use the starter kit's Supabase JWT auth as-is. No API key system. All callers including cron and scheduled Modal functions authenticate using a dedicated service account JWT stored as a Modal secret.
2. ~~**Resource schema:** Legacy has `job_id`, `insight_status`, `graphiti_status`. New design uses `pipeline_stage`. Phase 1 can introduce `pipeline_stage` from the start (values: `discovered`, `scraping`, `scraped`, etc.) or start minimal and add in Phase 2.~~ **RESOLVED:** Introduce `pipeline_stage` in Phase 1 from the start. Values: `discovered`, `scraping`, `scraped`, `extracting`, `extracted`, `ingesting`, `complete`, `failed`.
3. ~~**`scrape` flag:** Legacy has `scrape` (bool) for eligibility. Confirm whether to keep or derive from `pipeline_stage`.~~ **RESOLVED:** Drop the `scrape` flag. Eligibility is derived from `pipeline_stage` — anything in `discovered` is eligible to scrape.

---

### Phase 2: Scraping — Crawl4AI Integration

**What is being built**

- Crawl4AI integration for website and YouTube content extraction
- Modal scraping function: accepts `resource_id`, fetches content, stores on resource
- `pipeline_stage` transitions: `discovered` → `scraping` → `scraped`
- Removal of Apify, `jobs` table for scraping, and status polling

**Why at this point**

Insights and graph ingestion require scraped content. Scraping is the first processing step after discovery.

**Domains included**

- Scraping (reimplemented with Crawl4AI)

**Complexity**

Medium–large. Crawl4AI replaces Apify; YouTube vs website routing must be preserved. Modal function must handle timeouts, retries, and failure marking (`pipeline_stage = 'failed'`).

**Open questions / decisions**

1. ~~**Crawl4AI API:** Confirm Crawl4AI client usage (library vs self-hosted vs SaaS) and configuration.~~ **RESOLVED:** Use Crawl4AI as a Python library, running inside the existing `browser` tier Modal function (`process_browser_job`). The starter already defines this tier for `web_crawl` jobs (2 CPU, 2GB, 5min timeout, `browser_image`).
2. ~~**Content storage:** Where to store raw content — JSONB on `resource`, or separate table? Legacy stores on resource; preserve unless there are size limits.~~ **RESOLVED:** Store raw scraped content as a JSONB column on the `resource` row. Simple and co-located; revisit only if size becomes a problem.
3. ~~**Trigger:** In the new design, discovery spawns scrape directly. Phase 2 can implement a manual trigger (`POST /resources/scrape` for eligible resources) first, then wire to discovery in Phase 5.~~ **RESOLVED:** No manual trigger endpoint needed. The scrape Modal function is the trigger — it can be invoked directly via Modal CLI/dashboard at any time. Phase 2 builds the worker; Phase 5 wires discovery to spawn it.

---

### Phase 3: Insights — AI Extraction

**What is being built**

- Insight extraction agent (PydanticAI): entities, relationships, scored insights
- Modal function: reads scraped content, runs agent, stores `insight` JSONB
- `pipeline_stage`: `scraped` → `extracting` → `extracted`
- Entity/relationship taxonomy and scoring dimensions (importance, originality, reliability, relevance)
- Atomic selection + status update for race prevention
- Stuck-processing reset (configurable timeout)

**Why at this point**

Knowledge graph ingestion needs structured insight data. Insights depend on scraped content.

**Domains included**

- Insights

**Complexity**

Large. Agent design, retry logic, content validation (min length), and failure handling (disable scrape, mark failed) are non-trivial. Episode size constraints for downstream Graphiti should be considered.

**Open questions / decisions**

1. ~~**Alignment score:** Legacy model has `alignment` with "populated by secondary LLM" but that process is absent. Omit or implement?~~ **RESOLVED:** Omit entirely. Never implemented in legacy; not needed in the rebuild.
2. ~~**Retry strategy:** Legacy embeds JSON retries in agent. Prefer Modal retries + cleaner agent code.~~ **RESOLVED:** Use Modal-level retries. No retry logic inside the agent itself.
3. ~~**Model config:** Use `MODEL_INSIGHT_EXTRACTION` env var per desired-changes.~~ **RESOLVED:** Per-task env vars for all model config across the app. Each task gets its own env var: `MODEL_INSIGHT_EXTRACTION` (Phase 3), `MODEL_TRENDS` (Phase 6), `MODEL_CONTENT_GENERATION` and `MODEL_FACT_CHECK` (Phase 7). No global default — each must be explicitly set.

---

### Phase 4: Knowledge Graph — Graphiti Ingestion

**What is being built**

- Graphiti/Neo4j integration
- Modal function: reads insight JSONB, builds episodes, ingests sequentially
- Episode structure: atomic, focused content (one entity/relationship/fact per episode)
- `pipeline_stage`: `extracted` → `ingesting` → `complete`
- Stuck-processing reset (longer timeout than insights)

**Why at this point**

Trends and content generation query the graph. Graph ingestion depends on insights.

**Domains included**

- Knowledge Graph (Graphiti)

**Complexity**

Medium. Sequential ingestion and episode size constraints are documented. Connection retries (Neo4j, Graphiti) with backoff should be preserved.

**Open questions / decisions**

1. ~~**Neo4j/Graphiti hosting:** Confirm connection details and credentials (Infisical/Modal secrets).~~ **RESOLVED:** Neo4j Aura already provisioned. Env vars: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Add these to the Modal secrets for the worker app.
2. ~~**Episode validation:** Enforce <400 chars in code to avoid Graphiti LLM overflow.~~ **RESOLVED:** Two-layer approach: (1) Phase 3 insight extraction agent produces atomic, structured outputs (one entity/relationship/fact per insight) which naturally keeps episodes short; (2) Phase 4 adds a configurable `MAX_EPISODE_LENGTH` env var (default: 500 chars) with a validation/truncation step before ingestion as a safety net. Tune the limit after testing against the live Graphiti instance.

---

### Phase 5: Content Discovery — Sitemap and RSS

**What is being built**

- Sitemap scanner: parse sitemaps, filter by date/relevance/domain rules, deduplicate
- RSS support: parse feeds (explicit `known_rss_feeds`; auto-discovery deferred)
- Modal scheduled function (daily): runs discovery, submits URLs to `POST /resources`, spawns scrape for each new resource
- URL filtering: `days_back`, `min_relevance_score`, path patterns, `require_https`
- Dry-run mode for testing
- `sitemap_sources` Supabase table + migration script (replaces `sitemap_sources.json`)

**Why at this point**

Discovery feeds the pipeline. It depends on the resources API and the scrape spawn path. By Phase 5, scraping and ingestion are in place, so the full chain can run.

**Domains included**

- Content Discovery
- Scheduled Pipeline (discovery trigger)

**Complexity**

Medium. Filter pipeline and deduplication are well-specified. RSS auto-discovery is explicitly out of scope.

**Open questions / decisions**

1. ~~**Config source:** Legacy uses `sitemap_sources.json`; decide location and env overrides.~~ **RESOLVED:** Store sitemap/RSS sources in a Supabase `sitemap_sources` table (not a flat file). Include a migration script in Phase 5. This allows sources to be added/updated without a deploy.
2. ~~**Discovery → scrape handoff:** Spawn scrape for each new resource, or batch? Resource extraction planning suggests per-resource spawn to avoid blocking.~~ **RESOLVED:** Collect all new resources first, deduplicate against existing, then batch spawn scrape jobs for net-new resources only. Modal handles parallel spawning cleanly.

---

### ~~Phase 6: Trends — Multi-Agent Analysis~~ ELIMINATED

**Decision:** The multi-agent trends system and all chat endpoints (`POST /api/v1/trends/chat`, `WS /api/v1/trends/ws/{session_id}`) have been removed from the backend scope. Trend analysis will be handled by connecting an LLM directly to the Neo4j MCP server. The CMR backend's responsibility ends at Phase 4 — getting clean, structured data into the knowledge graph.

---

### ~~Phase 7: Content Generation~~ ELIMINATED

**Decision:** Content generation has been removed from the backend scope. Blog posts, newsletters, social posts, and reports are all LLM tasks that the frontend LLM client can handle directly using Neo4j MCP access — the same approach as Trends. No backend content generation endpoints needed.

---

### Phase 8: Pipeline Orchestration and Recovery

**What is being built**

- Unified pipeline: ensure discovery → scrape → insight → ingest chain is wired end-to-end
- Pipeline recovery: reset `failed` resources for retry, or periodic cleanup of stuck stages
- Manual triggers for each stage (for debugging/backfill)
- `POST /jobs/recover` (or equivalent) — starter may already have this; extend for resource pipeline jobs if needed

**Why at this point**

All pipeline stages exist. This phase ties them together, adds recovery semantics, and replaces the legacy cron chain with the new design.

**Domains included**

- Scheduled Pipeline (full orchestration)
- Recovery and cleanup

**Complexity**

Medium. Mostly wiring and configuration. Recovery logic for `pipeline_stage` (stuck `scraping`, `extracting`, `ingesting`) should mirror job recovery patterns.

**Open questions / decisions**

1. ~~**Failed resource retry:** Manual re-queue vs periodic job that resets `failed` → `discovered`?~~ **RESOLVED:** Manual re-queue only. Automatic retries risk hammering sites that have blocked Crawl4AI. A human should investigate the failure reason before deciding to retry. The resource record must store `failure_reason` (error type + message) so failed resources are actionable — not just a list of unknowns. Phase 1 should include `failure_reason` on the resource schema from the start.
2. ~~**Cleanup:** Legacy has placeholder `cleanup_completed_*_tasks`. Implement or remove.~~ **RESOLVED:** Remove entirely. Never implemented in legacy; no equivalent concern in the Modal architecture.

---

### ~~Phase 9: Tasks and Job Monitoring~~ ELIMINATED

**Decision:** The starter's existing jobs API (`GET /jobs`, `GET /jobs/{id}`) is sufficient as-is. With Phases 6 and 7 eliminated and the pipeline running through `pipeline_stage` on the resource record, there is nothing CMR-specific to add here.

---

## Deferred or Out of Scope

| Item | Reason |
|------|--------|
| **RSS auto-discovery** | Legacy: "not yet implemented." Requires explicit `known_rss_feeds`. Defer unless explicitly requested. |
| **Alignment score in insights** | Secondary LLM process absent; never implemented. Omitted from rebuild. |
| **Persona webhook** | Optional; silent fallback. Defer or implement with explicit error surfacing. |
| **Rate limiting per API key** | No API key system in new design. Not applicable. |
| **Cleanup of completed task results** | Legacy placeholders return 0. Redis/Celery result storage doesn't apply to Modal. No action unless Modal has equivalent storage to clean. |
| **Health check degradation** | Legacy: "degraded" if Neo4j down. Consider core vs optional dependencies in health model. |
| **Resource management CRUD** | Desired-changes mentions "add, remove, update resources" as future API. Not in initial scope. |
| **Sentry** | Desired-changes; implement when observability is prioritized. |

---

## Dependency Summary

```
Phase 1 (Foundation) → Phase 2 (Scraping) → Phase 3 (Insights) → Phase 4 (Knowledge Graph)
     │                       │                    │
     └───────────────────────┴────────────────────┴──→ Phase 5 (Discovery) → Phase 8 (Orchestration)
                                                                                      │
                                                                                      └──→ Phase 9 (Tasks)
```

No circular dependencies. Phases 6 (Trends) and 7 (Content Generation) have been eliminated — both are handled outside the backend via LLM + Neo4j MCP server. The backend's responsibility ends at Phase 4. Phase 5 (Discovery) depends on Phase 1 (Resources) and the scrape spawn path from Phase 2. Phase 8 wires the full pipeline after all stages exist.

---

## Spec Kit Usage

Each phase should be implemented as a separate speckit spec (e.g. `specs/002-resources-and-auth/`, `specs/003-scraping/`, etc.). The developer should:

1. Create a spec folder per phase
2. Include `plan.md`, `tasks.md`, and `quickstart.md` as needed
3. Reference this build plan for dependencies and open questions
4. Resolve open questions before or during the phase
5. Update this plan if scope or sequencing changes
