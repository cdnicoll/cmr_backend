"""PGMQ queue operations."""
import json

import asyncpg

from src.models.config import load_settings

QUEUE_NAME = "job_queue"


async def send_job_message(job_id: str, job_type: str, user_id: str, job_parameters: dict) -> int | None:
    """Send job message to PGMQ. Returns msg_id or None."""
    url = load_settings().transaction_pooler_url
    msg = json.dumps({"job_id": job_id, "job_type": job_type, "user_id": user_id, "job_parameters": job_parameters})
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT pgmq.send($1, $2) as msg_id", QUEUE_NAME, msg)
            return row["msg_id"] if row else None


async def read_job_messages(qty: int = 10, vt: int = 300) -> list[dict]:
    """Read messages from PGMQ. vt=visibility timeout in seconds."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pgmq.read(queue_name => $1, vt => $2, qty => $3)",
                QUEUE_NAME,
                vt,
                qty,
            )
            return [dict(r) for r in rows]


async def delete_job_message(msg_id: int) -> bool:
    """Delete message from PGMQ."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT pgmq.delete($1, $2) as deleted", QUEUE_NAME, msg_id)
            return bool(row and row["deleted"])
