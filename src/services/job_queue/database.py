"""Job database operations (asyncpg)."""
import asyncpg
from uuid import UUID
from datetime import datetime
from typing import Any

from src.models.config import load_settings
from src.models.jobs.job_status import JobStatus


async def get_pool() -> asyncpg.Pool:
    """Get asyncpg connection pool."""
    url = load_settings().transaction_pooler_url
    return await asyncpg.create_pool(
        url, min_size=1, max_size=5, command_timeout=60, statement_cache_size=0
    )


async def create_job(
    job_type: str,
    user_id: str,
    job_parameters: dict,
) -> dict[str, Any]:
    """Create a job and return it."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.jobs (job_type, status, user_id, job_parameters, retry_count)
                VALUES ($1, $2, $3, $4, 0)
                RETURNING id, job_type, status, user_id, job_parameters, retry_count,
                    created_at, updated_at, started_at, completed_at, error_message, error_type, data_references
                """,
                job_type,
                JobStatus.PENDING.value,
                user_id,
                asyncpg.Json(job_parameters),
            )
            return dict(row)


async def get_job_by_id(job_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    """Get job by ID; optionally filter by user_id for user-scoped access."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            if user_id:
                row = await conn.fetchrow(
                    "SELECT * FROM public.jobs WHERE id = $1 AND user_id = $2",
                    job_id,
                    user_id,
                )
            else:
                row = await conn.fetchrow("SELECT * FROM public.jobs WHERE id = $1", job_id)
            return dict(row) if row else None


async def update_job_status(
    job_id: str,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Update job status."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            if started_at is not None and completed_at is not None:
                await conn.execute(
                    """
                    UPDATE public.jobs SET status = $1, updated_at = NOW(), started_at = $2, completed_at = $3
                    WHERE id = $4
                    """,
                    status,
                    started_at,
                    completed_at,
                    job_id,
                )
            elif started_at is not None:
                await conn.execute(
                    """
                    UPDATE public.jobs SET status = $1, updated_at = NOW(), started_at = $2
                    WHERE id = $3
                    """,
                    status,
                    started_at,
                    job_id,
                )
            else:
                await conn.execute(
                    "UPDATE public.jobs SET status = $1, updated_at = NOW() WHERE id = $2",
                    status,
                    job_id,
                )


async def store_error_info(job_id: str, error_message: str, error_type: str, error_context: dict | None = None) -> None:
    """Store error info on job."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public.jobs SET error_message = $1, error_type = $2, error_context = $3, updated_at = NOW()
                WHERE id = $4
                """,
                error_message,
                error_type,
                asyncpg.Json(error_context or {}),
                job_id,
            )


async def store_data_references(job_id: str, data_references: dict) -> None:
    """Store data references on job."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE public.jobs SET data_references = $1, updated_at = NOW() WHERE id = $2",
                asyncpg.Json(data_references),
                job_id,
            )


async def list_jobs(
    user_id: str,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List jobs for user (user-scoped). Returns (items, total)."""
    url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            where = ["user_id = $1"]
            params: list[Any] = [user_id]
            n = 2
            if status:
                where.append(f"status = ${n}")
                params.append(status)
                n += 1
            if job_type:
                where.append(f"job_type = ${n}")
                params.append(job_type)
                n += 1

            where_clause = " AND ".join(where)
            count_row = await conn.fetchrow(
                f"SELECT COUNT(*)::int as c FROM public.jobs WHERE {where_clause}",
                *params,
            )
            total = count_row["c"] if count_row else 0

            params.extend([limit, offset])
            rows = await conn.fetch(
                f"""
                SELECT * FROM public.jobs WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${n} OFFSET ${n + 1}
                """,
                *params,
            )
            return [dict(r) for r in rows], total


async def find_stuck_jobs() -> list[dict[str, Any]]:
    """Find jobs stuck in processing (updated_at older than timeout)."""
    url = load_settings().transaction_pooler_url
    timeout_min = load_settings().job_stuck_timeout_minutes
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM public.jobs
                WHERE status = 'processing' AND updated_at < NOW() - INTERVAL '1 minute' * $1
                """,
                timeout_min,
            )
            return [dict(r) for r in rows]


async def find_orphaned_jobs() -> list[dict[str, Any]]:
    """Find orphaned pending jobs (created_at older than timeout)."""
    url = load_settings().transaction_pooler_url
    timeout_min = load_settings().job_stuck_timeout_minutes
    async with asyncpg.create_pool(
        url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM public.jobs
                WHERE status = 'pending' AND created_at < NOW() - INTERVAL '1 minute' * $1 AND retry_count < 2
                """,
                timeout_min,
            )
            return [dict(r) for r in rows]


async def mark_job_failed(job_id: str, error_message: str, error_type: str) -> None:
    """Mark job as failed."""
    await update_job_status(job_id, JobStatus.FAILED.value)
    await store_error_info(job_id, error_message, error_type)
