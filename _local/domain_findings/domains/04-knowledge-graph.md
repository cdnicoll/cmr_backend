# Domain: Knowledge Graph (Graphiti)

## Purpose

The Knowledge Graph domain ingests **insights into Neo4j** via Graphiti. It converts each insight into a minimal "episode" that Graphiti's LLM processes to extract entities and relationships, building a queryable graph for trends and content generation.

## Core Behavior

1. **Manual ingest trigger** (`POST /api/v1/resources/insight/ingest`):
   - Queries resources where: `insight IS NOT NULL`, `graphiti_status='pending'`, within publication window
   - Atomically marks as `graphiti_status='processing'`
   - Queues Celery task per resource

2. **Graphiti task flow** (`process_resource_to_knowledge_graph`):
   - Fetches resource + insight from PostgreSQL
   - Builds episodes: one episode per insight (via `build_resource_episodes`)
   - Each episode: ultra-minimal content (<400 chars) with insight text, source URL, channel, reference date
   - Adds episodes to Graphiti sequentially (required for entity resolution)
   - On success: sets `graphiti_ingested_at`, `graphiti_status='completed'`

3. **Episode structure**: `ResourceGraphEpisode` with `episode_content` dict containing insight, source_url, channel, reference_date — Graphiti extracts sub-entities from text

## Key Data

- **resource columns**: `graphiti_status` (pending|processing|completed|failed), `graphiti_ingested_at`
- **Graphiti**: Uses `graphiti_core` with Neo4j; episodes added via `add_episode` (JSON source)
- **EpisodeType**: `json` for episode body

## Boundaries

- **Depends on**: Neo4j, Graphiti, PostgreSQL, insight data
- **Depended on by**: Trends service (queries graph), Content generation (Neo4j intelligence)

## Edge Cases and Notable Logic

- **Sequential processing**: Graphiti requires episodes added one-by-one for proper entity resolution
- **Episode size**: Target <400 chars to avoid LLM context overflow
- **JSON parsing failures**: Graphiti's internal LLM can fail; task marks `graphiti_status='failed'`, no retry
- **Stuck processing**: `reset_processing_graphiti_resources(max_age_minutes=120)` — longer than insight reset
- **Connection errors**: Retried (Neo4jConnectionError, GraphitiConnectionError) with exponential backoff

## What to Preserve

- One episode per insight, minimal content
- Sequential ingestion requirement
- Status tracking (pending/processing/completed/failed) for race prevention
- Stuck-reset with longer timeout than insights
