"""Modal worker functions."""
import asyncio
import os

import modal

# Environment-driven app name (set by deploy script or .env)
_env = os.environ.get("ENVIRONMENT", "develop")
app = modal.App(f"CMR-{_env}")

# Base image: pip deps only (add_local must be last per Modal)
image_base = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"PYTHONUNBUFFERED": "1"})
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

# Discovery image: feedparser (RSS) + YouTube Data API client for run_discovery
discovery_image = (
    image_base
    .pip_install("feedparser", "google-api-python-client")
    .add_local_python_source("src")
)

# Browser image: Crawl4AI + Playwright — add_local must be last
# Pin requests>=2.32 to avoid RequestsDependencyWarning with urllib3 2.x / charset_normalizer 3.x
browser_image = (
    image_base
    .pip_install("requests>=2.32.0", "crawl4ai", "playwright", "youtube-transcript-api")
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
    """Scrape a resource by ID. Updates pipeline_stage and scraped_content. On success, spawns ingest."""
    from src.services.scraping.service import scrape_resource as _scrape

    await _scrape(resource_id)
    await ingest_resource.spawn.aio(resource_id)


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
    image=discovery_image,
    timeout=600,  # 10 min for tens of sources
    schedule=modal.Period(hours=6),
    secrets=_secrets,
)
async def run_discovery(dry_run: bool = False) -> None:
    """Daily discovery: sitemap/RSS/YouTube → net-new resources → spawn scrape for created only."""
    from src.utils.logging import get_logger

    from src.services.discovery.service import run_discovery as _run_discovery

    logger = get_logger(__name__)
    created_ids = await _run_discovery(dry_run=dry_run)
    if dry_run:
        logger.info("DRY RUN: no resources created, no scrape spawned.")
        return
    if created_ids:
        await asyncio.gather(*[scrape_resource.spawn.aio(str(rid)) for rid in created_ids])


@app.function(
    image=image,
    timeout=300,
    schedule=modal.Period(hours=2),
    secrets=_secrets,
)
async def run_recovery_pipeline() -> None:
    """Scheduled recovery: mark resources stuck in scraping/ingesting as failed."""
    from src.services.orchestration.recovery import run_recovery_pipeline as _run_recovery

    await _run_recovery()


