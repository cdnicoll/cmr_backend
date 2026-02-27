# Domain: Content Generation

## Purpose

The Content Generation domain produces **AI-generated content** (blogs, newsletters, reports, social posts) grounded in the knowledge graph. It uses a multi-agent pipeline with Neo4j intelligence gathering, generation, and fact-checking.

## Core Behavior

1. **Queue generation** (`POST /api/v1/trend-analysis/content`):
   - Requires at least one selected entity
   - Creates pending record in `generated_content` table **before** queueing (prevents race)
   - Queues Celery task with priority 9
   - Returns 202 with `task_id`, `status_url`

2. **Content task flow** (`generate_content_async`):
   - Supervisor agent orchestrates: Neo4j intelligence → Generation → Fact-check
   - **Neo4j intelligence**: Fetches entity/relationship data, temporal patterns, correlations
   - **Generation agent**: Produces content based on content_type, focus, tone, length
   - **Fact-check agent**: Validates claims against sources
   - Stores result in `generated_content`, updates task status

3. **Polling**: Client polls `GET /task/{task_id}` for status; `GET /task/{task_id}/result` for completed content

## Key Data

- **Content types**: blog, newsletter, social, report
- **Content focus**: entity-trends, relationship-analysis, temporal-patterns, market-impact, investment-insights, industry-overview
- **Fact check levels**: basic, standard, comprehensive
- **generated_content table**: session_id, task_id, request_data, result, status

## Boundaries

- **Depends on**: Neo4jIntelligenceService, Content supervisor/generation/fact-check agents, ContentStorageService, Celery
- **Depended on by**: None (leaf consumer)

## Edge Cases and Notable Logic

- **Race condition fix**: Pending record created before `apply_async` so status endpoint can find task before Celery picks it up
- **Persona service**: Optional — fetches AI persona from webhook for tone; falls back to default on failure
- **Health check**: Validates supervisor and sub-agents; if supervisor fails, tests each component individually

## What to Preserve

- Pending-record-before-queue pattern for async content
- Multi-step pipeline (intelligence → generate → fact-check)
- Entity selection as required input
- Content type/focus/tone/length options
