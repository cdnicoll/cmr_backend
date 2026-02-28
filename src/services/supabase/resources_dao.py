"""Resources DAO — asyncpg-based CRUD for resources table."""
import asyncpg

from src.models.config import load_settings
from src.models.resources import PipelineStage


async def insert_resource(url: str, resource_type: str) -> dict | None:
    """
    Insert a new resource. Returns the inserted row or None on unique constraint violation (duplicate).
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(db_url, min_size=1, max_size=5) as pool:
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO public.resources (url, type, pipeline_stage)
                    VALUES ($1, $2, $3)
                    RETURNING id, url, title, type, pipeline_stage, failure_reason,
                        scraped_content, insight, discovery_source_id, created_at, updated_at
                    """,
                    url,
                    resource_type,
                    PipelineStage.DISCOVERED.value,
                )
                return dict(row) if row else None
            except asyncpg.UniqueViolationError:
                return None


async def get_resource_by_url(url: str) -> dict | None:
    """Get resource by URL. Returns None if not found."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(db_url, min_size=1, max_size=5) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, url, title, type, pipeline_stage FROM public.resources WHERE url = $1",
                url,
            )
            return dict(row) if row else None
