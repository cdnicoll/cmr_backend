"""Discovery sources DAO — list enabled sources, get by id."""
import asyncpg

from src.models.config import load_settings


async def list_enabled_sources() -> list[dict]:
    """Return all discovery_sources rows where enabled = true. Order not specified."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, source_type, name, config, enabled, created_at, updated_at, first_run_at
                FROM public.discovery_sources
                WHERE enabled = true
                """
            )
            return [dict(r) for r in rows]


async def get_by_id(source_id: str) -> dict | None:
    """Get a single discovery source by id. Returns None if not found."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, source_type, name, config, enabled, created_at, updated_at, first_run_at
                FROM public.discovery_sources
                WHERE id = $1
                """,
                source_id,
            )
            return dict(row) if row else None


async def update_first_run_at(source_id: str) -> None:
    """Mark source as having completed its first discovery run. Idempotent."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public.discovery_sources
                SET first_run_at = COALESCE(first_run_at, NOW())
                WHERE id = $1
                """,
                source_id,
            )
