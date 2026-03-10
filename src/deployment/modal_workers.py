"""Modal worker functions."""
import os

import modal

# Environment-driven app name (set by deploy script or .env)
_env = os.environ.get("ENVIRONMENT", "develop")
app = modal.App(f"Job-Worker-{_env}")

# Base image: pip deps only (add_local must be last per Modal)
image_base = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi",
        "uvicorn",
        "supabase",
        "pyjwt[crypto]",
        "cryptography",
        "sqlalchemy[asyncio]",
        "asyncpg",
        "pydantic",
        "pydantic-settings",
        "httpx",
        "python-dotenv",
        "pydantic-ai==1.0.5",
        "openai",
        "graphiti-core",
    )
)

# Standard image for most workers
image = image_base.add_local_python_source("src")

# Browser image: Crawl4AI + Playwright — add_local must be last
browser_image = (
    image_base
    .pip_install("crawl4ai", "playwright", "youtube-transcript-api")
    .apt_install(
        # Chromium/Playwright system deps (per crawl-for-ai-modal-implementation.md)
        "libglib2.0-0",
        "libnss3",
        "libnspr4",
        "libatk1.0-0",
        "libatk-bridge2.0-0",
        "libcups2",
        "libdrm2",
        "libdbus-1-3",
        "libxkbcommon0",
        "libxcomposite1",
        "libxdamage1",
        "libxfixes3",
        "libxrandr2",
        "libgbm1",
        "libasound2",
        "libpango-1.0-0",
        "libcairo2",
        "libatspi2.0-0",
        "libxshmfence1",
    )
    .run_commands("playwright install chromium")
    .add_local_python_source("src")
)

# Modal secrets for DB/config (create via scripts/create_modal_secrets.sh)
_secrets = [
    modal.Secret.from_name(f"supabase-credentials-{_env}"),
    modal.Secret.from_name(f"app-config-{_env}"),
]


@app.function(
    image=browser_image,
    timeout=300,
    cpu=2,
    memory=2048,
    retries=1,
    secrets=_secrets,
)
async def scrape_resource(resource_id: str) -> None:
    """Scrape a resource by ID. Updates pipeline_stage and scraped_content."""
    from src.services.scraping.service import scrape_resource as _scrape

    await _scrape(resource_id)


@app.function(
    image=image,
    timeout=300,
    secrets=_secrets,
)
async def process_sample_job(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> None:
    """Process sample_task job."""
    await _process_job(job_id, job_type, user_id, job_parameters)


# Tiered workers (stubs for future job types per modal-jobs.md)
@app.function(
    image=image,
    timeout=900,  # 15 min
    cpu=4,
    memory=8192,  # 8GB
    secrets=_secrets,
)
async def process_gpu_job(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> None:
    """Process GPU-tier jobs (e.g. document_index)."""
    await _process_job(job_id, job_type, user_id, job_parameters)


@app.function(
    image=image,
    timeout=300,  # 5 min
    cpu=2,
    memory=2048,  # 2GB
    secrets=_secrets,
)
async def process_browser_job(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> None:
    """Process browser-tier jobs (e.g. web_crawl)."""
    await _process_job(job_id, job_type, user_id, job_parameters)


@app.function(
    image=image,
    timeout=300,  # 5 min
    cpu=1,
    memory=1024,  # 1GB
    secrets=_secrets,
)
async def process_llm_job(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> None:
    """Process LLM-tier jobs (e.g. document_process, llm_task)."""
    await _process_job(job_id, job_type, user_id, job_parameters)


@app.function(
    image=image,
    timeout=600,  # 10 min — generous for Graphiti/LLM and Neo4j
    cpu=2,
    memory=2048,
    retries=1,
    max_containers=10,  # cap parallel ingest jobs; queue excess (Neo4j/OpenAI friendly)
    secrets=_secrets,
)
async def ingest_resource(resource_id: str) -> None:
    """Ingest scraped resource into knowledge graph (Graphiti). Updates pipeline_stage to complete or failed."""
    from src.services.ingestion.service import ingest_resource as _ingest

    await _ingest(resource_id)


@app.function(
    image=image,
    timeout=120,  # 2 min
    cpu=0.5,
    memory=512,
    secrets=_secrets,
)
async def process_api_job(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> None:
    """Process API-tier jobs (e.g. company_enrich)."""
    await _process_job(job_id, job_type, user_id, job_parameters)


@app.function(
    image=image,
    timeout=300,
    schedule=modal.Period(minutes=15),
    secrets=_secrets,
)
async def recover_orphaned_jobs() -> None:
    """Scheduled recovery: mark stuck and orphaned jobs as failed."""
    from src.services.job_queue import database

    stuck = await database.find_stuck_jobs()
    orphaned = await database.find_orphaned_jobs()

    for job in stuck:
        await database.mark_job_failed(
            str(job["id"]),
            "Job exceeded maximum processing time",
            "JobTimeoutError",
        )
    for job in orphaned:
        await database.mark_job_failed(
            str(job["id"]),
            "Job never started (pending timeout)",
            "PendingTimeoutError",
        )


async def _process_job(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> None:
    """Shared job processing logic."""
    from src.services.job_queue.service import JobQueueService

    svc = JobQueueService()
    await svc.process_job(job_id, job_type, user_id, job_parameters)
