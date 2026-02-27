# Resource Extraction Pipeline — Redesign Planning

A more detailed breakdown of the proposed architecture to replace the current implicit cron-driven pipeline with an explicit, event-driven, async-native workflow.

---

## Goals

- Replace five loosely-coupled cron jobs with a single, explicitly-ordered pipeline
- Eliminate dual status columns (`insight_status`, `graphiti_status`) in favour of a unified resource state
- Remove Celery + `asyncio.run()` friction with async-native task execution via Modal
- Replace Apify's job/poll/dataset indirection with direct scraping via Crawl4AI
- Retain all existing deduplication guarantees

---

## Unified Resource State

Replace `insight_status` and `graphiti_status` with a single `pipeline_stage` column.

| Stage | Description |
|-------|-------------|
| `discovered` | URL accepted into the system; not yet scraped |
| `scraping` | Crawl4AI job in progress |
| `scraped` | Raw content retrieved and stored |
| `extracting` | AI insight extraction in progress |
| `extracted` | Entities, relationships, and insights populated |
| `ingesting` | Graphiti/Neo4j ingestion in progress |
| `complete` | Resource fully processed and in the knowledge graph |
| `failed` | Terminal failure at any stage; failure reason recorded |

**Benefits over the current approach:**
- One column captures the full lifecycle — no ambiguity between two parallel statuses
- Reset and retry logic lives in one place
- Simple to query: "where is this resource right now?"
- Timeout/resurrection logic is stage-specific and explicit

---

## Technology Changes

| Concern | Current | Proposed |
|---------|---------|----------|
| Database | Neon (PostgreSQL) | Supabase (PostgreSQL) |
| Scraping | Apify (external actor jobs) | Crawl4AI (direct, in-process) |
| Task execution | Celery + Redis | Modal (async-native functions) |
| Pipeline orchestration | 5 independent cron jobs | Modal scheduled function + chained calls |
| Logging / observability | Logfire | Sentry |

---

## Pipeline Architecture

The pipeline is modelled as a composed chain of Modal functions. Each step is responsible for completing its work and directly invoking the next step — there is no polling or external scheduler coordinating the handoff.

### Overview

```
[Modal Scheduled Function — daily]
        │
        ▼
  [ Discovery ]
  Parse sitemaps + RSS feeds for configured sources
  Filter by: date window, relevance score, domain rules
  Deduplicate within batch
        │
        ▼
  POST /resources (Supabase)
  Unique constraint deduplicates against existing records
  New URLs inserted with pipeline_stage = 'discovered'
        │
        ▼ (for each new resource, spawn in parallel)
  [ Scraping — Modal Function ]
  Crawl4AI fetches page content (website or YouTube)
  Content stored on resource record
  pipeline_stage → 'scraped'
        │
        ▼
  [ Insight Extraction — Modal Function ]
  AI extracts entities, relationships, scored insights
  Results stored as JSONB on resource
  pipeline_stage → 'extracted'
        │
        ▼
  [ Graph Ingestion — Modal Function ]
  Graphiti writes entities + relationships to Neo4j
  pipeline_stage → 'complete'
```

---

## Step-by-Step Detail

### 1. Discovery (Modal Scheduled Function)

Runs on a daily schedule. Replaces the current `sitemap_scanner` cron job.

- Loads source config (sitemap URLs, RSS feeds, filter rules)
- For each source:
  - Fetches and parses sitemap XML or RSS feed
  - Filters URLs by date (`days_back`), relevance score, domain path rules
  - Deduplicates within the batch
- Submits all discovered URLs in batches to `POST /api/v1/resources`
- The API's unique constraint on `url` silently skips anything already known
- For each newly created resource, spawns a Modal scrape function

**Key difference from current:** Discovery directly chains into scraping rather than waiting for a separate cron job to pick up `pending` records on its own schedule.

---

### 2. Scraping (Modal Function)

Replaces Apify actor jobs and the job status polling cron.

- Receives a `resource_id` and `url`
- Sets `pipeline_stage = 'scraping'`
- Calls Crawl4AI to extract content:
  - For websites: full page text, metadata, publication date
  - For YouTube: transcript, title, channel metadata
- Stores extracted content on the resource record
- Sets `pipeline_stage = 'scraped'`
- Directly invokes the insight extraction function

**Key difference from current:** No external job creation, no `data_id` to poll for, no resurrection logic. Crawl4AI returns content directly. Modal handles retries if the function fails.

---

### 3. Insight Extraction (Modal Function)

Replaces the Celery `process_resource_insight` task.

- Receives a `resource_id`
- Sets `pipeline_stage = 'extracting'`
- Passes scraped content to the AI insight agent (PydanticAI / configured LLM)
- Agent extracts:
  - Named entities (companies, people, commodities)
  - Relationships between entities
  - Scored insights (relevance, significance)
- Stores result as JSONB on the resource record
- Sets `pipeline_stage = 'extracted'`
- Directly invokes the graph ingestion function

**Key difference from current:** No `asyncio.run()` wrapping a sync Celery task. The Modal function is async-native throughout. Retry logic is handled by Modal, not embedded in the agent's `run_agent` method.

---

### 4. Graph Ingestion (Modal Function)

Replaces the Celery `process_resource_to_knowledge_graph` task.

- Receives a `resource_id`
- Sets `pipeline_stage = 'ingesting'`
- Reads the insight JSONB from the resource record
- Submits entities and relationships to Graphiti for Neo4j ingestion
- Sets `pipeline_stage = 'complete'`

**Key difference from current:** No separate ingest cron needed. The step fires immediately when extraction completes.

---

## Error Handling and Retries

Modal provides built-in retry configuration per function. Each pipeline step should be configured with:

- A **retry count** appropriate to the operation (e.g. 3 retries for scraping, 2 for AI extraction)
- An **exponential backoff** policy
- On terminal failure: set `pipeline_stage = 'failed'` and record the stage and error reason on the resource

This replaces the current timeout-based reset logic and resurrection semantics with a clearer, modal-native approach. A failed resource can be manually re-queued or picked up by a periodic cleanup job that resets `failed` records back to `discovered`.

---

## Deduplication (Unchanged)

The deduplication strategy is preserved exactly:

1. **Within a discovery batch** — the sitemap scanner deduplicates URLs before submission
2. **At the database** — the unique constraint on `resource.url` silently skips known URLs

No resource can enter the pipeline twice. A URL discovered in this week's sitemap scan that was already processed last week will be submitted, skipped at the API, and no pipeline work will be spawned.

---

## Model Configuration

As noted in desired changes, all LLM models should be defined via environment variables so they can be swapped without code changes.

| Variable | Purpose |
|----------|---------|
| `MODEL_INSIGHT_EXTRACTION` | Model used in the insight extraction agent |
| `MODEL_CONTENT_GENERATION` | Model used for blog/newsletter/report generation |
| `MODEL_TRENDS_ANALYSIS` | Model used in the trends multi-agent workflow |

---

## What This Eliminates

| Current Component | Replaced By |
|-------------------|-------------|
| Scraper cron job | Modal scheduled discovery function |
| Status polling cron job | Crawl4AI direct return (no polling needed) |
| Insight queue cron job | Direct chaining from scrape → extract |
| Graph ingest cron job | Direct chaining from extract → ingest |
| `insight_status` column | Unified `pipeline_stage` |
| `graphiti_status` column | Unified `pipeline_stage` |
| `jobs` table (Apify job tracking) | Eliminated — no external job lifecycle to manage |
| Celery + Redis | Modal |
| `asyncio.run()` in tasks | Native async Modal functions |

---

## What to Preserve

- SSRF protection and URL validation on resource intake
- Dual discovery mechanisms: sitemap XML and RSS
- Filter pipeline: date → relevance → domain rules → deduplication
- Batch submission to the resources API
- Dry-run mode for testing discovery without API submission
- Resource type detection (website vs YouTube) for routing to correct Crawl4AI extractor
- 200 + empty response semantics for "no work" endpoints
- Graphiti episode size constraints (target <400 chars per episode)
