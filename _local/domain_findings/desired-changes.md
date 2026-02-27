# Desired Changes

Documentation of changes to pursue at a later time. No solutions or implementation details — just intent.

---

## Infrastructure

- **Replace Neon with Supabase** — Move from Neon PostgreSQL to Supabase (PostgreSQL + ecosystem).

- **Replace Apify with Crawl4AI** — Replace Apify scraping with Crawl4AI for web and YouTube content extraction.

- **Replace Celery with Modal** — Replace Celery/Redis task queue with Modal for background job execution.

- **Use Sentry for logging** — Replace or augment current logging (Logfire) with Sentry.

---

## Configuration

- **Model swapping via environment variables** — Define AI/LLM models in environment variables so they can be swapped easily (e.g. different models for insight extraction, content generation, trends analysis) without code changes.

---

## API

- **Resource management endpoints** — API endpoints to add, remove, and update resources (e.g. YouTube URLs, websites to scrape). Full CRUD for the resource catalog.

---
