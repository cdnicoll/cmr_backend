# CMR Application Overview

## What the Application Does

**CMR (Content Mining & Research)** is a backend platform for the **mining industry**. It:

1. **Discovers** content — Finds URLs from mining industry websites (sitemaps, RSS feeds)
2. **Scrapes** content — Extracts text and metadata from web pages and videos via Apify
3. **Analyzes** content — Uses AI to identify entities (companies, commodities, people), relationships, and insights
4. **Builds a knowledge graph** — Stores entities and relationships in Neo4j (via Graphiti) for querying
5. **Surfaces intelligence** — Exposes APIs for trend analysis and AI-generated content grounded in the graph

In plain terms: CMR continuously monitors mining industry sources, pulls in new content, runs it through AI to extract who and what matters, and builds a searchable graph. Clients can ask for trends or request AI-generated reports, newsletters, or summaries based on that graph.

---

## Identified Domains

| Domain | One-line Summary |
|--------|------------------|
| **Resources** | URL lifecycle management — validation, storage, duplicate handling |
| **Scraping** | Apify-powered content extraction; job creation and status polling |
| **Insights** | AI extraction of entities, relationships, and scored insights from scraped content |
| **Knowledge Graph** | Graphiti/Neo4j ingestion of insights into queryable graph |
| **Trends** | Multi-agent trend analysis with knowledge graph + optional external data |
| **Content Generation** | AI-generated blogs, newsletters, reports with fact-checking |
| **Authentication** | API key validation, optional/required auth, scopes |
| **Content Discovery** | Cron: sitemap/RSS scanning, URL submission to API |
| **Scheduled Pipeline** | Cron: scraper, status check, insight queue, graph ingest |
| **Tasks** | Generic Celery task status, list, cancel (debugging/monitoring) |

---

## Data Flow

```
[Content Discovery Cron]  →  POST /resources (URLs)
                                    ↓
                            [resource table: pending]
                                    ↓
[Scraper Cron]            →  POST /resources/scrape
                                    ↓
                            [Apify jobs created]
                                    ↓
[Status Cron]             →  GET /resources/scrape/status
                                    ↓
                            [jobs.data_id populated]
                                    ↓
[Status Cron]             →  POST /resources/insight
                                    ↓
                            [Celery: process_resource_insight]
                                    ↓
                            [resource.insight populated]
                                    ↓
[Insight Ingest Cron]     →  POST /resources/insight/ingest
                                    ↓
                            [Celery: process_resource_to_knowledge_graph]
                                    ↓
                            [Neo4j graph via Graphiti]
                                    ↓
[Trends API]              ←  Query graph + optional external data
[Content API]             ←  Generate content from graph
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **API** | FastAPI |
| **Async** | asyncio, asyncpg |
| **Task queue** | Celery, Redis |
| **Database** | PostgreSQL (resource, jobs, api_keys, generated_content) |
| **Graph** | Neo4j, Graphiti |
| **Scraping** | Apify |
| **AI** | PydanticAI, OpenAI (gpt-4o, gpt-4o-mini) |
| **Observability** | Logfire |
| **Rate limiting** | SlowAPI |
| **Auth** | Bearer API keys (DB-stored) |

---

## Patterns and Conventions

- **No ORM**: Raw SQL with asyncpg; context manager `get_db_connection()`
- **Status columns for race prevention**: `insight_status`, `graphiti_status` with atomic `UPDATE ... RETURNING`
- **Empty = 200**: "No eligible resources" returns 200 with empty counts, not 404
- **Celery for heavy work**: Insight extraction, Graphiti ingestion, content generation
- **Service layer**: API routes delegate to services (ResourceService, ScrapingJobService, etc.)
- **Pydantic models**: Request/response validation; strict typing
- **Entity-specific primary keys** (per CLAUDE.md): `resource_id`, `job_id` — though current schema uses `id` in some tables
