"""TSXV50 snapshots DAO — asyncpg-based reads and writes for tsxv50_snapshots table."""
import json

import asyncpg

from src.models.config import load_settings


def _decode_jsonb(value):
    """asyncpg may return jsonb columns as raw JSON text or as decoded objects
    depending on codec configuration; normalize to decoded Python objects."""
    return json.loads(value) if isinstance(value, str) else value


async def get_latest_snapshot() -> dict | None:
    """Return the most recent snapshot row or None if the table is empty."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, symbols, entries, created_at FROM public.tsxv50_snapshots ORDER BY created_at DESC LIMIT 1"
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "symbols": _decode_jsonb(row["symbols"]),
                "entries": _decode_jsonb(row["entries"]),
                "created_at": row["created_at"],
            }


async def list_snapshots() -> list[dict]:
    """List every watchlist snapshot, newest first: {id, created_at, entry_count,
    has_entries}. This is the membership history — what it is for is saying which
    companies joined or left the watchlist between two editions with a date behind
    the claim, instead of an impression. Contents deliberately excluded; call
    get_snapshot for those."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    created_at,
                    CASE
                        WHEN jsonb_typeof(entries) = 'array' THEN jsonb_array_length(entries)
                        WHEN jsonb_typeof(symbols) = 'array' THEN jsonb_array_length(symbols)
                        ELSE 0
                    END AS entry_count,
                    entries IS NOT NULL AS has_entries
                FROM public.tsxv50_snapshots
                ORDER BY created_at DESC
                """
            )
            return [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "entry_count": row["entry_count"],
                    "has_entries": row["has_entries"],
                }
                for row in rows
            ]


async def get_snapshot(snapshot_id: int) -> dict | None:
    """Return one snapshot by id, or None if it doesn't exist. `entries`
    ({symbol, name, category}) is populated on snapshots taken after migration 008;
    older rows carry only the legacy `symbols` array, which is why both are returned
    rather than one normalized field."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, symbols, entries, created_at
                FROM public.tsxv50_snapshots WHERE id = $1
                """,
                snapshot_id,
            )
            if not row:
                return None
            return {
                "id": row["id"],
                "symbols": _decode_jsonb(row["symbols"]),
                "entries": _decode_jsonb(row["entries"]),
                "created_at": row["created_at"],
            }


async def insert_snapshot_entries(entries: list[dict]) -> dict:
    """Insert a new snapshot row with `entries` populated and return the inserted row."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.tsxv50_snapshots (entries)
                VALUES ($1)
                RETURNING id, symbols, entries, created_at
                """,
                json.dumps(entries),
            )
            return {
                "id": row["id"],
                "symbols": _decode_jsonb(row["symbols"]),
                "entries": _decode_jsonb(row["entries"]),
                "created_at": row["created_at"],
            }
