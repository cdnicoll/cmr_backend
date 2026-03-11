# CMR Rebuild — Phased Build Plan

## Current status

**Complete:** Phase 1 (Foundation), Phase 2 (Scraping — Crawl4AI), Phase 2b (YouTube), Phase 4 (Knowledge Graph — Graphiti Ingestion from scraped content), Phase 5 (Content Discovery), Phase 8 (Pipeline Orchestration and Recovery). Phase 3 (Insights) was superseded; Graphiti is the single extractor and Phase 4 removed the Phase 3 extraction code.  
**Runbook:** Commands for each pipeline stage (resources, scrape, ingest, recovery, re-queue) are in `docs/runbook.md`.

---

## Overview

This plan describes how to rebuild the **CMR (Content Mining & Research)** backend — a mining industry content intelligence platform — using the modern starter kit. The legacy app discovers URLs from mining sources, scrapes content via Apify, extracts entities and insights with AI, ingests them into a Neo4j knowledge graph via Graphiti, and exposes trend analysis and AI-generated content APIs. The rebuild will migrate to Supabase, Modal, and Crawl4AI while unifying the pipeline state and replacing implicit cron orchestration with an explicit, event-driven workflow.

---

## What Exists in the Starter

The starter kit already provides:

| Component | Status |
|-----------|--------|
| **FastAPI app** | Entry point, lifespan, middleware (CORS, metrics, rate limit, request ID) |
| **Supabase** | Client factory, PostgREST, RLS |
| **Transaction pooler** | asyncpg for resources, discovery_sources, etc. (PGMQ removed) |
| **Auth** | JWT verification via Supabase JWKS, `get_current_user`, `get_validated_jwt_user` |
| **Jobs** | **Removed for CMR.** No `jobs` table, no PGMQ, no POST /jobs; pipeline uses only resource pipeline. |
| **Modal** | Three workers only: run_discovery (scheduled), scrape_resource, ingest_resource; no process_*_job tiers, no recover_orphaned_jobs. |
| **Health** | `/health`, `/health/db` |
| **Patterns** | Service → DAO; no job queue API. |
| **Recovery** | **Removed** (recover_orphaned_jobs dropped); Phase 8 adds resource-pipeline recovery (stuck scraping/ingesting). |
| **Migration** | Script pattern; 006_drop_jobs removes jobs table and PGMQ. |

**Not present and must be built:** Resources domain, scraping (Crawl4AI), Graphiti/Neo4j ingestion (from scraped content; Graphiti is the single extractor), content discovery, and the resource pipeline orchestration. (No separate "insights agent" — extraction is done by Graphiti during ingestion.)

---

## Stack Changes to Keep in Mind

| Concern | Legacy | New Stack | Impact |
|---------|--------|-----------|--------|
| **Database** | Neon (PostgreSQL) | Supabase (PostgreSQL) | Same SQL; use Supabase client + asyncpg pooler. RLS may apply for user-scoped data. |
| **Scraping** | Apify (external jobs, poll for `data_id`) | Crawl4AI (direct, in-process) | No `jobs` table for Apify; no status polling cron. Scraping becomes a Modal function that returns content directly. |
| **Task queue** | Celery + Redis | Modal | Replace Celery tasks with Modal functions. No `asyncio.run()` in sync tasks — Modal is async-native. |
| **Auth** | Bearer API keys (DB-stored) | Supabase Auth (JWT) | Starter uses JWT. All callers including cron and scheduled Modal functions authenticate using a dedicated service account JWT stored as a Modal secret. No changes needed to the starter's existing auth implementation. |
| **Pipeline orchestration** | 5 independent cron jobs | Modal scheduled + chained calls | Discovery runs on schedule; scrape → insight → ingest chain directly. No implicit ordering. |
| **Resource state** | `insight_status` + `graphiti_status` (dual columns) | Single `pipeline_stage` | Unified lifecycle: discovered → scraping → scraped → ingesting → complete / failed. (No separate extraction stage — Graphiti does extraction during ingestion.) |
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
2. ~~**Resource schema:** Legacy has `job_id`, `insight_status`, `graphiti_status`. New design uses `pipeline_stage`. Phase 1 can introduce `pipeline_stage` from the start (values: `discovered`, `scraping`, `scraped`, etc.) or start minimal and add in Phase 2.~~ **RESOLVED:** Introduce `pipeline_stage` in Phase 1 from the start. Values: `discovered`, `scraping`, `scraped`, `ingesting`, `complete`, `failed`. (Graphiti is the single extractor; no separate extracting/extracted stages.)
3. ~~**`scrape` flag:** Legacy has `scrape` (bool) for eligibility. Confirm whether to keep or derive from `pipeline_stage`.~~ **RESOLVED:** Drop the `scrape` flag. Eligibility is derived from `pipeline_stage` — anything in `discovered` is eligible to scrape.

**How to test**

- `GET /health` and `GET /health/db` return 200
- `POST /api/v1/resources` with a valid URL returns 201 and the resource appears in Supabase with `pipeline_stage = discovered`
- `POST /api/v1/resources` with the same URL again returns 200 (skipped, no duplicate created)
- `POST /api/v1/resources` with an invalid or SSRF URL returns 422
- `POST /api/v1/resources` with a YouTube URL is detected as type `youtube`
- Query Supabase directly to confirm the `resource` table schema matches spec (including `pipeline_stage`, `failure_reason`)
- Hit a protected endpoint without a JWT — confirm 401

---

### Phase 2: Scraping — Crawl4AI Integration

**What is being built**

- Crawl4AI integration for website and YouTube content extraction
- Modal scraping function: accepts `resource_id`, fetches content, stores on resource
- `pipeline_stage` transitions: `discovered` → `scraping` → `scraped`
- Removal of Apify, `jobs` table for scraping, and status polling
- `max_containers = 8` on `scrape_resource` — Modal queues excess spawns automatically (see Phase 2b)

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

**How to test**

- In the Modal dashboard, spawn the scrape worker with a known `resource_id` (a resource in `discovered` stage)
- Confirm the resource transitions: `discovered` → `scraping` → `scraped` in Supabase
- Confirm the `scraped_content` JSONB column is populated on the resource row
- Repeat with a YouTube URL — confirm YouTube extraction path runs correctly
- Spawn the worker against a URL known to block scrapers — confirm `pipeline_stage = failed` and `failure_reason` is populated

---

### Phase 2b: YouTube Scraping

**What is being built**

- YouTube transcript extraction using `youtube-transcript-api` (Crawl4AI does not support YouTube)
- Extend the existing `scrape_resource` Modal function to route `type = youtube` resources to the YouTube extraction path
- Same `pipeline_stage` transitions as Phase 2: `discovered` → `scraping` → `scraped` (or `failed`)
- Same `scraped_content` JSONB structure — transcript stored as `markdown`, `metadata.type = youtube`
- Handle videos with disabled or unavailable captions → `pipeline_stage = failed`, `failure_reason` populated
- Minimum content length check (same `SCRAPE_MIN_WORD_COUNT` threshold as Phase 2)

**Why at this point**

Phase 2 established the scraping pattern and `scraped_content` schema for websites. YouTube extraction uses a different library (no browser required — `youtube-transcript-api` fetches captions directly) but follows the identical worker pattern. Phase 4 (Graphiti ingestion) requires scraped content for all resource types before it can run.

**Domains included**

- Scraping (YouTube path only)

**Complexity**

Small. The pattern is identical to Phase 2; only the extraction library differs. No new tables, no new Modal functions — extends the existing `scrape_resource` worker.

**Open questions / decisions**

1. ~~**YouTube extraction library**~~ **RESOLVED:** Use `youtube-transcript-api`. Crawl4AI does not support YouTube. Fetches captions directly from YouTube's caption API — lightweight, no browser required, raises clear exceptions when captions are unavailable.
2. ~~**Scrape worker concurrency**~~ **RESOLVED:** Set `max_containers = 8` on the `scrape_resource` Modal function. Modal queues spawns beyond 8 and processes them as containers free up. This controls cost, prevents hammering target sites, and reduces the risk of IP blocks. Applies to both website and YouTube scraping.

**How to test**

- Create a resource with a YouTube URL (`pipeline_stage = discovered`)
- Spawn `scrape_resource` with the YouTube resource ID via Modal CLI/dashboard
- Confirm `pipeline_stage = scraped` and `scraped_content.markdown` contains the transcript
- Confirm `scraped_content.metadata.type = youtube`
- Spawn against a YouTube video with disabled captions — confirm `pipeline_stage = failed` and `failure_reason` populated

---

### Phase 3: Insights — Superseded by Phase 4 (Graphiti as single extractor)

**Design decision (Option B2):** Graphiti is the single extractor for the knowledge graph. There is no separate "insight extraction" step that writes structured JSON to Supabase for the graph. The pipeline is: **scraped → ingesting → complete**.

**Current state:** Phase 3 was previously implemented with a PydanticAI extraction agent that wrote an `insight` JSONB column. That code remains in the repo but is **deprecated**. As part of **Phase 4**, we will:
- Implement the Graphiti ingestion worker that reads `scraped_content` (markdown + metadata) and sends it to Graphiti; Graphiti performs LLM-based entity/relationship extraction, entity merge, and writes to Neo4j.
- **Remove** the Phase 3 extraction code: insight agent, `InsightsService.extract_insights`, `extract_insights` Modal function, DAO methods used only for extraction, `insight`-related models/config, and the `extracting`/`extracted` pipeline stages from use.

**Phase 3 (as redefined) is therefore:** Validation only — e.g. minimum word count on `scraped_content` before a resource is eligible for ingestion. That validation can live in the Phase 4 ingestion worker (reject or mark `failed` if content too short) or in a thin pre-step. No separate Phase 3 spec is required for new work; the existing `specs/004-insights/` material is historical. Phase 4 spec and implementation cover both "ingest via Graphiti" and "remove Phase 3 extraction code."

---

### Phase 4: Knowledge Graph — Graphiti Ingestion (from scraped content)

**What is being built**

- Graphiti/Neo4j integration: **ingestion from scraped content** (not from a pre-extracted insight JSON). The worker reads `scraped_content` (e.g. `markdown`, optional title/url) and sends it to Graphiti as episode(s). Graphiti runs its own LLM-based extraction, entity merge, temporal edges, and writes Entity, Episodic, RELATES_TO, MENTIONS to Neo4j.
- Modal function: accepts `resource_id`, fetches resource and `scraped_content`, validates (e.g. min word count), transitions to `ingesting`, calls Graphiti to add episode(s), on success sets `pipeline_stage = complete`, on failure sets `failed` and `failure_reason`.
- `pipeline_stage`: `scraped` → `ingesting` → `complete` (or `failed`). No `extracting`/`extracted` stages.
- **Removal of Phase 3 extraction code** (same phase): Remove the PydanticAI insight agent, `InsightsService.extract_insights`, `extract_insights` Modal function, DAO methods used only for extraction (`atomic_transition_to_extracting`, `update_resource_after_extraction`), `insight`-related models and config, and update runbook/docs. Optionally deprecate or drop the `insight` column on `resources` (or leave unpopulated).
- Stuck-processing reset for `ingesting` (configurable timeout); recovery worker in Phase 8 will reset stuck resources.

**Why at this point**

Trends and content generation query the graph. Graph ingestion depends on scraped content. Using Graphiti as the single extractor matches the legacy design and keeps one source of truth (Graphiti's entity merge and temporal handling).

**Domains included**

- Knowledge Graph (Graphiti)
- Cleanup of superseded Phase 3 extraction (agent, service, Modal, DAO, config)

**Complexity**

Medium. Graphiti's add-episode (or equivalent) API, connection retries (Neo4j, Graphiti), and env/credentials. Plus removal of Phase 3 extraction code and pipeline/wiring updates.

**Open questions / decisions**

1. ~~**Neo4j/Graphiti hosting:** Confirm connection details and credentials (Infisical/Modal secrets).~~ **RESOLVED:** Neo4j Aura already provisioned. Env vars: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Add these to the Modal secrets for the worker app.
2. **Episode content:** Graphiti ingests text (and optionally structured metadata). Worker passes `scraped_content.markdown` plus resource url/title/source as needed for Graphiti's episode format. Graphiti handles episode size and entity extraction; configure `MAX_EPISODE_LENGTH` or Graphiti equivalents if documented.
3. **Entity/relationship alignment:** The existing Neo4j graph (Entity by `name`, RELATES_TO with SCREAMING_SNAKE type) was built by Graphiti. Feeding scraped text to Graphiti preserves that; Graphiti performs entity merge so new content (e.g. about "Gold") attaches to existing nodes.

**How to test**

- Spawn the Graphiti ingestion worker with a `resource_id` (resource in `scraped` stage with valid `scraped_content`)
- Confirm the resource transitions: `scraped` → `ingesting` → `complete` in Supabase
- Open the Neo4j console and verify new Entity/Episodic/RELATES_TO/MENTIONS from the ingested content
- Spawn against a resource with very short or missing content — confirm `pipeline_stage = failed` and `failure_reason` set
- After Phase 4 code changes: confirm the old `extract_insights` path is removed and the runbook reflects ingest-only flow

**Phase 4 pre-plan (before spec planning)**

Resolve or document the following so the Phase 4 spec can be concrete:

1. **Graphiti API (confirmed):** Use `add_episode()` for single-resource ingestion. Signature: `await graphiti.add_episode(name=..., episode_body=..., source=EpisodeType.text, source_description=..., reference_time=...)`. For scraped content, pass `episode_body=scraped_content.markdown`, `source=EpisodeType.text`. See [Adding Episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes). Spec should define: `name` (e.g. resource id or `resource_{uuid}`), `source_description` (e.g. resource url or title for provenance), `reference_time` (resource `updated_at` or `created_at` vs `datetime.now()`).

2. **Runtime dependencies:** Ingestion worker needs `graphiti-core`, Neo4j driver (included with Graphiti), and an LLM/embedder. Graphiti defaults to OpenAI; optional extras for Anthropic, Groq, etc. Add to Phase 4 scope: install `graphiti-core` (and optional extras if not using OpenAI), configure Graphiti with `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` plus LLM/embedder env (e.g. `OPENAI_API_KEY`) in Modal secrets. Document in spec.

3. **Minimum content for ingestion:** Decide env var and default (e.g. `INGEST_MIN_WORD_COUNT`, default 100). Worker rejects or marks `failed` if `scraped_content` is missing or word count below threshold. Spec should include this validation step.

4. **Stuck `ingesting` timeout:** For Phase 8 recovery, define a configurable timeout (e.g. `INGEST_STUCK_TIMEOUT_MINUTES`, default 30). Phase 4 can add the config; Phase 8 recovery worker uses it to reset stuck resources. Spec can note it; implementation in Phase 8.

5. **Runbook:** Phase 4 implementation must update `docs/runbook.md`: replace "Insight extraction (Phase 3)" with "Ingest to Graphiti", new worker command (e.g. `modal run ...::ingest_resource --resource-id <uuid>`), verify `scraped` → `ingesting` → `complete`.

---

### Phase 5: Content Discovery — Sitemap, RSS, and YouTube

**What is being built**

- `discovery_sources` Supabase table + migration script — stores all monitored sources with a `source_type` column: `sitemap`, `rss`, `youtube_channel`
- Sitemap scanner: parse XML sitemaps, filter by date/relevance/domain rules, deduplicate
- RSS scanner: parse feeds from `rss` entries in `discovery_sources` (auto-discovery deferred)
- YouTube channel scanner: fetch latest videos from a channel, extract video URLs as resources
- Modal scheduled function (daily): runs all three scanners, submits new URLs to `POST /resources`, batch spawns scrape jobs for net-new resources
- URL filtering: `days_back`, `min_relevance_score`, path patterns, `require_https`
- Dry-run mode for testing
- `discovery_sources` Supabase table + migration script (replaces `discovery_sources.json`)

**Why at this point**

Discovery feeds the pipeline. It depends on the resources API and the scrape spawn path. By Phase 5, scraping and ingestion are in place, so the full chain can run.

**Domains included**

- Content Discovery
- Scheduled Pipeline (discovery trigger)

**Complexity**

Medium. Filter pipeline and deduplication are well-specified. RSS auto-discovery is explicitly out of scope.

**Open questions / decisions**

1. ~~**Config source:** Legacy uses `discovery_sources.json`; decide location and env overrides.~~ **RESOLVED:** Store all discovery sources in a Supabase `discovery_sources` table with a `source_type` column (`sitemap`, `rss`, `youtube_channel`). Replaces the legacy flat file. Include a migration script in Phase 5. Sources can be added/updated without a deploy.
2. ~~**Discovery → scrape handoff:** Spawn scrape for each new resource, or batch? Resource extraction planning suggests per-resource spawn to avoid blocking.~~ **RESOLVED:** Collect all new resources first, deduplicate against existing, then batch spawn scrape jobs for net-new resources only. Modal handles parallel spawning cleanly.

**How to test**

- Confirm the `discovery_sources` table exists in Supabase after the migration script runs
- Insert one row of each `source_type` (`sitemap`, `rss`, `youtube_channel`) into `discovery_sources` directly in Supabase
- In the Modal dashboard, trigger the discovery function manually (dry-run mode first) — confirm it reads from the table and logs what it would create for each source type
- Run discovery for real — confirm new resources appear in Supabase with `pipeline_stage = discovered` for both URL and YouTube video URL types
- Confirm duplicate URLs are skipped (run discovery twice — no duplicate resources created)
- Confirm scrape jobs are batch-spawned for net-new resources after discovery completes

---

### ~~Phase 6: Trends — Multi-Agent Analysis~~ ELIMINATED

**Decision:** The multi-agent trends system and all chat endpoints (`POST /api/v1/trends/chat`, `WS /api/v1/trends/ws/{session_id}`) have been removed from the backend scope. Trend analysis will be handled by connecting an LLM directly to the Neo4j MCP server. The CMR backend's responsibility ends at Phase 4 — getting clean, structured data into the knowledge graph.

---

### ~~Phase 7: Content Generation~~ ELIMINATED

**Decision:** Content generation has been removed from the backend scope. Blog posts, newsletters, social posts, and reports are all LLM tasks that the frontend LLM client can handle directly using Neo4j MCP access — the same approach as Trends. No backend content generation endpoints needed.

---

### Phase 8: Pipeline Orchestration and Recovery

**What is being built**

- Unified pipeline: ensure discovery → scrape → ingest (Graphiti) chain is wired end-to-end (scrape spawns ingest on success)
- Scheduled recovery: a Modal function (e.g. every 15 min) that finds resources stuck in `scraping` or `ingesting` (older than configurable timeouts) and marks them `failed` with a clear reason; no jobs table or `POST /jobs/recover` — recovery applies only to resource `pipeline_stage`
- Manual re-queue: operators reset failed resources to `discovered` via runbook (SQL + Modal re-trigger) and optionally `POST /api/v1/resources/{id}/requeue`
- Manual triggers for each stage (discovery dry-run, scrape one, ingest one) documented in runbook for debugging/backfill

**Why at this point**

All pipeline stages exist. This phase ties them together, adds recovery semantics, and replaces the legacy cron chain with the new design.

**Domains included**

- Scheduled Pipeline (full orchestration)
- Recovery and cleanup

**Complexity**

Medium. Mostly wiring and configuration. Recovery logic for `pipeline_stage` (stuck `scraping`, `ingesting`) should mirror job recovery patterns.

**Open questions / decisions**

1. ~~**Failed resource retry:** Manual re-queue vs periodic job that resets `failed` → `discovered`?~~ **RESOLVED:** Manual re-queue only. Automatic retries risk hammering sites that have blocked Crawl4AI. A human should investigate the failure reason before deciding to retry. The resource record must store `failure_reason` (error type + message) so failed resources are actionable — not just a list of unknowns. Phase 1 should include `failure_reason` on the resource schema from the start.
2. ~~**Cleanup:** Legacy has placeholder `cleanup_completed_*_tasks`. Implement or remove.~~ **RESOLVED:** Remove entirely. Never implemented in legacy; no equivalent concern in the Modal architecture.

**How to test**

- Trigger the full pipeline end-to-end: insert a source into `discovery_sources`, run discovery, confirm resources flow through all `pipeline_stage` values to `complete` and appear in Neo4j
- Simulate a stuck resource (manually set `pipeline_stage = scraping` with an old `updated_at`) — confirm the recovery worker resets it to `failed` with a timeout reason
- Manually re-queue a failed resource (reset `pipeline_stage = discovered`) — confirm it re-enters the pipeline correctly
- Confirm resources stuck in `ingesting` are also caught by the recovery worker
- Check the Modal dashboard — confirm all scheduled functions (discovery, recovery) are registered and firing on their expected schedules

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
Phase 1 (Foundation) → Phase 2 (Website Scraping) → Phase 2b (YouTube) → Phase 4 (Graphiti Ingestion from scraped content)
     │                       │                              │
     └───────────────────────┴──────────────────────────────┴──────────────────────────────→ Phase 5 (Discovery) → Phase 8 (Orchestration)
```

No circular dependencies. Phase 3 (Insights) as originally implemented is superseded: Graphiti is the single extractor; Phase 4 implements ingestion from scraped content and removes the Phase 3 extraction code. Phases 6 (Trends) and 7 (Content Generation) are eliminated — handled outside the backend via LLM + Neo4j MCP. The backend's responsibility ends at Phase 4. Phase 2b must complete before Phase 4 (ingestion needs scraped content for all types). Phase 5 (Discovery) depends on Phase 1 and the scrape spawn path; orchestration (Phase 8) wires discovery → scrape → ingest.

---

## Spec Kit Usage

Each phase should be implemented as a separate speckit spec (e.g. `specs/002-resources-and-auth/`, `specs/003-scraping/`, etc.). The developer should:

1. Create a spec folder per phase
2. Include `plan.md`, `tasks.md`, and `quickstart.md` as needed
3. Reference this build plan for dependencies and open questions
4. Resolve open questions before or during the phase
5. Update this plan if scope or sequencing changes
