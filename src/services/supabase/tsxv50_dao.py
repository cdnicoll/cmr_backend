"""TSXV50 snapshots DAO — asyncpg-based reads and writes for tsxv50_snapshots table."""
import json

import asyncpg

from src.models.config import load_settings


async def get_latest_snapshot() -> dict | None:
    """Return the most recent snapshot row or None if the table is empty."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, symbols, created_at FROM public.tsxv50_snapshots ORDER BY created_at DESC LIMIT 1"
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "symbols": row["symbols"],
                "created_at": row["created_at"],
            }


async def insert_snapshot(symbols: list[str]) -> dict:
    """Insert a new snapshot row and return the inserted row."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.tsxv50_snapshots (symbols)
                VALUES ($1)
                RETURNING id, symbols, created_at
                """,
                json.dumps(symbols),
            )
            return {
                "id": row["id"],
                "symbols": row["symbols"],
                "created_at": row["created_at"],
            }
