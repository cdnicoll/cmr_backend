# Crawl for AI + Modal Implementation Guide

**SDG Backend** — Detailed technical documentation of how web crawling (crawl4AI) is integrated with Modal for ESG report discovery.

**Last Updated**: 2025-02-27

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Entry Points](#entry-points)
4. [Modal Deployment](#modal-deployment)
5. [Job Queue Flow](#job-queue-flow)
6. [Crawl4AI Integration](#crawl4ai-integration)
7. [PDF Processing Pipeline](#pdf-processing-pipeline)
8. [Storage and Database](#storage-and-database)
9. [Configuration and Secrets](#configuration-and-secrets)
10. [File Reference](#file-reference)

---

## Overview

The SDG Backend uses **crawl4AI** for web crawling to discover ESG (Environmental, Social, Governance) reports on company websites. Crawling runs on **Modal** in a tiered worker architecture, with browser-based jobs using a dedicated image that includes Playwright/Chromium.

**Key characteristics:**
- **crawl4AI** with optional LLM extraction (OpenAI GPT-4o-mini) or keyword-based fallback
- **Modal** for serverless execution with right-sized resources (2 CPU, 2GB RAM, 5 min timeout)
- **Job queue** for async processing via API; CLI for direct/local runs
- **Supabase** for storage (PDFs) and database (metadata, job state)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINTS                                    │
├─────────────────────────────────┬─────────────────────────────────────────┤
│  API (Production)                 │  CLI (Development / Direct)             │
│  POST /companies/{id}/esg/discover│  python -m src.cli.esg_crawler.main      │
│  → JobQueueService.create_job()   │  → crawl_command() → ESGCrawlService    │
└─────────────────────────────────┴─────────────────────────────────────────┘
                    │                                    │
                    ▼                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│  JOB QUEUE PATH (API only)                                                    │
│  create_job() → spawn_job() → Modal process_browser_job()                   │
│  → JobQueueService.process_job() → ESGCrawlService.crawl_company_website()   │
└─────────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ESG CRAWL SERVICE (shared by API job path and CLI)                           │
│  ESGCrawlService.crawl_company_website()                                      │
│  → _crawl_with_llm() or _crawl_with_keywords()                               │
│  → PDF download → validate → upload to Supabase Storage → create DB record   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Entry Points

### 1. API (Job Queue Path)

**Endpoint**: `POST /companies/{company_id}/esg/discover`

**Flow:**
1. Authenticated user calls the endpoint.
2. `JobQueueService.create_job()` validates parameters, checks for duplicates, creates a job record.
3. Job is sent to PGMQ (backup) and **spawned immediately** via `spawn_job()`.
4. `spawn_job()` maps `esg_discover` → `process_browser_job` and calls `modal.Function.from_name(...).spawn()`.
5. Modal runs `process_browser_job()` on the **browser image** (crawl4ai, Playwright, Chromium).
6. `process_browser_job()` calls `JobQueueService.process_job()`, which invokes `ESGCrawlService.crawl_company_website()`.
7. Results are stored in `jobs.data_references` and job status is updated.

**Relevant files:**
- `src/api/routes/companies.py` — `discover_esg_reports()`
- `src/services/job_queue/service.py` — `create_job()`, `process_job()` (esg_discover branch)
- `src/services/job_queue/spawner.py` — `spawn_job()`, `JOB_TIER_MAPPING`

### 2. CLI (Direct / Local Development)

**Command:**
```bash
python -m src.cli.esg_crawler.main --company-id <UUID> [--user-id <UUID>]
```

**Flow:**
1. Loads settings from `.env` (Supabase, optional OpenAI).
2. Creates Supabase client and `ESGCrawlService`.
3. Calls `crawl_command()` → `ESGCrawlService.crawl_company_website()`.
4. Outputs `CrawlResult` as JSON.

**Relevant files:**
- `src/cli/esg_crawler/main.py` — argument parsing, orchestration
- `src/cli/esg_crawler/commands.py` — `crawl_command()`, validation, error handling

---

## Modal Deployment

### Two Modal Apps

| App | Purpose | Crawl-related |
|-----|---------|---------------|
| **SDG-API** | FastAPI web app | Includes crawl4ai in image; no crawl function |
| **SDG-Job-Worker** | Background job processing | `process_browser_job` runs ESG crawl |

Crawl execution happens in **SDG-Job-Worker**, not in the API app.

### Tiered Workers

Jobs are routed by `JOB_TIER_MAPPING` in `src/services/job_queue/spawner.py`:

```python
JOB_TIER_MAPPING = {
    "esg_index": "process_gpu_job",      # GPU tier
    "esg_discover": "process_browser_job", # Browser tier ← CRAWL
    "esg_process": "process_llm_job",
    # ... assessments → process_llm_job
    "company_enrich": "process_api_job",
}
```

### Browser Tier Configuration

**File**: `src/deployment/modal_workers.py`

```python
browser_image = (
    Image.debian_slim(python_version="3.11")
    .pip_install(*_base_packages)
    .pip_install(
        "crawl4ai>=0.3.0",
        "playwright>=1.40.0",
        "PyPDF2>=3.0.0",
    )
    .apt_install(
        # Chromium/Playwright system deps
        "libglib2.0-0", "libnss3", "libnspr4", "libatk1.0-0",
        "libatk-bridge2.0-0", "libcups2", "libdrm2", "libdbus-1-3",
        "libxkbcommon0", "libxcomposite1", "libxdamage1", "libxfixes3",
        "libxrandr2", "libgbm1", "libasound2", "libpango-1.0-0",
        "libcairo2", "libatspi2.0-0", "libxshmfence1",
    )
    .run_commands("playwright install chromium")
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("data", remote_path="/root/data")
)

@app.function(
    image=browser_image,
    secrets=secrets,
    timeout=300,       # 5 minutes
    cpu=2.0,
    memory=2048,       # 2GB
    max_containers=5,
    region="ca",
)
async def process_browser_job(job_id, job_type, user_id, job_parameters):
    await _process_job(job_id, job_type, user_id, job_parameters)
```

### Spawn Mechanism

`spawn_job()` uses the Modal SDK to invoke the deployed function by name:

```python
fn = modal.Function.from_name(worker_app_name, function_name)
fn.spawn(
    job_id=str(job_id),
    job_type=job_type,
    user_id=str(user_id),
    job_parameters=job_parameters,
)
```

- `worker_app_name`: e.g. `SDG-Job-Worker-production` (from `MODAL_WORKER_APP_NAME` or `ENVIRONMENT`)
- `function_name`: `process_browser_job` for `esg_discover`

---

## Job Queue Flow

### create_job() → spawn_job()

1. Validate `company_id` exists.
2. Check for duplicate pending/processing job for same company.
3. Add `user_id` to `job_parameters` (from JWT).
4. Insert job into `jobs` table.
5. Send message to PGMQ (backup).
6. Call `spawn_job()` to start Modal worker.

### process_job() for esg_discover

1. Update job status to `processing`.
2. Resolve `company_id` and `user_id` from `job_parameters`.
3. Instantiate `ESGCrawlService` with Supabase client and optional OpenAI key.
4. Call `crawl_service.crawl_company_website(company_id, user_id)`.
5. Build `data_references` from stored reports (id, report_name, report_year, doc_path, doc_url).
6. Store `data_references` in `jobs` table.
7. Update job status to `completed`.

---

## Crawl4AI Integration

**File**: `src/services/esg_crawl/crawler.py`

### ESGCrawlService

- **Input**: Supabase client, optional OpenAI API key.
- **Output**: `CrawlResult` (counts, discoveries, errors, duration).

### Crawl Strategies

#### 1. LLM Extraction (when OpenAI key is present)

- Uses `LLMExtractionStrategy` with schema:
  - `page_url`, `page_title`, `is_esg_report`, `confidence_score`, `report_type`, `download_links`, `description`
- Model: `openai/gpt-4o-mini`
- Instruction: analyze page for ESG reports, sustainability reports, CSR, PDF links.
- Crawls homepage first, then ESG-related internal links (same domain).
- Max pages: 500 (configurable via `CrawlConfig.max_pages`).

#### 2. Keyword Fallback (no OpenAI key)

- Uses `CrawlRunConfig` without LLM extraction.
- Filters links by ESG keywords: `esg`, `sustainability`, `environmental`, `social`, `governance`, `csr`, `impact report`, `climate`, `carbon`, etc.
- Extracts PDF links from crawled pages.
- Same domain and page limits apply.

### Crawler Configuration

```python
browser_config = BrowserConfig(headless=True, verbose=False)
run_config = CrawlerRunConfig(
    extraction_strategy=extraction_strategy,  # or None for keyword mode
    cache_mode=CacheMode.BYPASS,
    word_count_threshold=50,
)
```

### Domain and Page Limits

- **Same domain**: Only links with same `urlparse().netloc` as base URL.
- **Max pages**: 500 (configurable).
- **PDF detection**: URL ends with `.pdf` or path contains `.pdf`.

### Result Processing

- Extracts `download_links` from crawl results.
- Filters by `is_esg_report` or `confidence_score >= 0.5`.
- Sorts by confidence and ESG flag.
- For each PDF: duplicate check → download → validate → upload → create DB record.

---

## PDF Processing Pipeline

**Files**: `src/services/esg_crawl/pdf_processor.py`, `storage.py`, `database.py`

### 1. Duplicate Check

- Query `esg_reports` by `source_location` (PDF URL).
- Skip download and storage if duplicate.

### 2. Download

- `download_pdf(url)` via `httpx.AsyncClient`.
- Timeout: 30 seconds.
- Validates `Content-Type: application/pdf` or `.pdf` extension.

### 3. Validation

- Magic bytes: `%PDF`.
- Optional version check: `%PDF-1.x` or `%PDF-2.x`.

### 4. Metadata Extraction

- `extract_filename_from_url()` — handles paths like `file.pdf/segment?query=param`.
- `extract_metadata_from_filename()` — year (regex 1900–2100), report name (cleaned).
- Year defaults to current year if not found.

### 5. Storage Path

- Format: `{company_id}/{year}_{sanitized_name}.pdf`
- Bucket: `esg-reports`

### 6. Upload

- Supabase Storage: `supabase_client.storage.from_(bucket).upload(...)`.
- Content-Type: `application/pdf`.

### 7. Database Record

- Table: `esg_reports`
- Fields: `company_id`, `report_year`, `report_name`, `doc_path`, `doc_url`, `source_location`, `created_by_user_id`, `updated_by_user_id`.

---

## Storage and Database

### Supabase Storage

- **Bucket**: `esg-reports`
- **Path**: `{company_id}/{year}_{report_name}.pdf`
- **Public URL**: via `get_public_url()`

### Database Tables

| Table | Purpose |
|-------|---------|
| `companies` | Website URL for crawl |
| `esg_reports` | Report metadata, doc_path, doc_url, source_location |
| `jobs` | Job status, data_references (reports_created, storage_paths) |

### Duplicate Handling

- `source_location` used for deduplication.
- Duplicates: skip download/storage, increment `reports_duplicates`, add to discoveries with `duplicate=True`.

---

## Configuration and Secrets

### ESG Crawl Settings

**File**: `src/services/esg_crawl/settings.py`

- `SUPABASE_URL` — required
- `SUPABASE_SECRET_KEY` — required
- `OPENAI_API_KEY` — optional (enables LLM extraction)

### Modal Secrets (Worker)

- `supabase-credentials-{ENVIRONMENT}` — Supabase URL and keys
- `app-config-{ENVIRONMENT}` — `MODAL_WORKER_APP_NAME`, `ENVIRONMENT`, etc.
- `llm-credentials-{ENVIRONMENT}` — `OPENAI_API_KEY` for LLM extraction

### Environment Variables

- `ENVIRONMENT` — `production`, `develop`, `test`
- `MODAL_WORKER_APP_NAME` — e.g. `SDG-Job-Worker-production`
- `JOB_QUEUE_NAME` — PGMQ queue name (default: `job_queue`)

---

## File Reference

| Path | Purpose |
|------|---------|
| `src/services/esg_crawl/crawler.py` | Main crawl logic, crawl4AI, LLM/keyword strategies |
| `src/services/esg_crawl/database.py` | Company lookup, report CRUD, duplicate check |
| `src/services/esg_crawl/storage.py` | Path generation, upload, public URL |
| `src/services/esg_crawl/pdf_processor.py` | Download, validate, metadata extraction |
| `src/services/esg_crawl/settings.py` | ESG crawl config |
| `src/services/esg_crawl/exceptions.py` | Custom exceptions |
| `src/cli/esg_crawler/main.py` | CLI entry point |
| `src/cli/esg_crawler/commands.py` | `crawl_command` handler |
| `src/deployment/modal_workers.py` | Browser tier, `process_browser_job` |
| `src/services/job_queue/spawner.py` | Job → Modal function mapping |
| `src/services/job_queue/service.py` | `create_job`, `process_job` (esg_discover) |
| `src/models/esg/crawl_result.py` | `CrawlResult`, `ReportDiscovery`, `CrawlConfig` |
| `src/api/routes/companies.py` | `POST /companies/{id}/esg/discover` |

---

## Summary

The crawl-for-AI + Modal setup in SDG Backend:

1. Uses **crawl4AI** with optional LLM extraction or keyword fallback.
2. Runs on **Modal** via the **browser tier** (`process_browser_job`) with Playwright/Chromium.
3. Is triggered by the **API** (job queue) or **CLI** (direct).
4. Downloads PDFs, validates them, uploads to Supabase Storage, and creates `esg_reports` records.
5. Deduplicates by `source_location` and stores job results in `jobs.data_references`.
