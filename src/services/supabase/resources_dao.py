"""Resources DAO — asyncpg-based CRUD for resources table."""
import json

import asyncpg

from src.models.config import load_settings
from src.models.resources import PipelineStage


async def get_resource_by_id(resource_id: str) -> dict | None:
    """Get resource by ID. Returns None if not found."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, url, title, type, pipeline_stage, failure_reason,
                    scraped_content, discovery_source_id, created_at, updated_at
                FROM public.resources WHERE id = $1
                """,
                resource_id,
            )
            return dict(row) if row else None


async def atomic_transition_to_scraping(resource_id: str) -> int:
    """
    Atomically transition pipeline_stage from discovered to scraping.
    Returns number of rows updated (1 if claimed, 0 if already claimed or not discovered).
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.resources
                SET pipeline_stage = $1
                WHERE id = $2 AND pipeline_stage = $3
                """,
                PipelineStage.SCRAPING.value,
                resource_id,
                PipelineStage.DISCOVERED.value,
            )
            # result is like "UPDATE 1" or "UPDATE 0"
            return int(result.split()[-1]) if result else 0


async def atomic_transition_to_ingesting(resource_id: str) -> int:
    """
    Atomically transition pipeline_stage from scraped to ingesting.
    Returns number of rows updated (1 if claimed, 0 if already claimed or not scraped).
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE public.resources
                SET pipeline_stage = $1
                WHERE id = $2 AND pipeline_stage = $3
                """,
                PipelineStage.INGESTING.value,
                resource_id,
                PipelineStage.SCRAPED.value,
            )
            return int(result.split()[-1]) if result else 0


async def update_resource_after_ingestion(
    resource_id: str,
    pipeline_stage: str,
    failure_reason: str | None = None,
) -> None:
    """
    Update resource after ingestion attempt.
    Sets pipeline_stage and optionally failure_reason.
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public.resources
                SET pipeline_stage = $1, failure_reason = $2
                WHERE id = $3
                """,
                pipeline_stage,
                failure_reason,
                resource_id,
            )


async def update_resource_after_scrape(
    resource_id: str,
    pipeline_stage: str,
    scraped_content: dict | None = None,
    failure_reason: str | None = None,
) -> None:
    """
    Update resource after scrape attempt.
    Sets pipeline_stage, and optionally scraped_content (JSONB) or failure_reason.
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public.resources
                SET pipeline_stage = $1, scraped_content = $2, failure_reason = $3
                WHERE id = $4
                """,
                pipeline_stage,
                json.dumps(scraped_content) if scraped_content else None,
                failure_reason,
                resource_id,
            )


async def insert_resource(
    url: str,
    resource_type: str,
    discovery_source_id: str | None = None,
) -> dict | None:
    """
    Insert a new resource. Returns the inserted row or None on unique constraint violation (duplicate).
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO public.resources (url, type, pipeline_stage, discovery_source_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, url, title, type, pipeline_stage, failure_reason,
                        scraped_content, discovery_source_id, created_at, updated_at
                    """,
                    url,
                    resource_type,
                    PipelineStage.DISCOVERED.value,
                    discovery_source_id,
                )
                return dict(row) if row else None
            except asyncpg.UniqueViolationError:
                return None


async def get_existing_urls(urls: list[str]) -> set[str]:
    """Return the set of URLs that already exist in resources. Used for deduplication."""
    if not urls:
        return set()
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT url FROM public.resources WHERE url = ANY($1::text[])",
                urls,
            )
            return {r["url"] for r in rows}


async def get_resource_by_url(url: str) -> dict | None:
    """Get resource by URL. Returns None if not found."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, url, title, type, pipeline_stage FROM public.resources WHERE url = $1",
                url,
            )
            return dict(row) if row else None
