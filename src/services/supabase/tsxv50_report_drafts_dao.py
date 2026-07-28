"""TSXV50 report drafts DAO — asyncpg-based reads and writes for tsxv50_report_drafts.

One row per draft, keyed by (period_label, draft_slug). Category writes use
jsonb_set/`||` against the current row value so concurrent per-category writes
(from parallel category-researcher/category-drafter subagents) never lose an
update to a different category key.
"""
import json

import asyncpg

from src.models.config import load_settings

_COLUMNS = """
    id, period_label, draft_slug, status, meta, master_list, introduction, categories,
    synthesis, finalize_result, conversation_ids, pdf_url, created_at, updated_at
"""


def _decode_jsonb(value):
    """asyncpg may return jsonb columns as raw JSON text or as decoded objects
    depending on codec configuration; normalize to decoded Python objects."""
    return json.loads(value) if isinstance(value, str) else value


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "period_label": row["period_label"],
        "draft_slug": row["draft_slug"],
        "status": row["status"],
        "meta": _decode_jsonb(row["meta"]),
        "master_list": _decode_jsonb(row["master_list"]),
        "introduction": _decode_jsonb(row["introduction"]),
        "categories": _decode_jsonb(row["categories"]),
        "synthesis": _decode_jsonb(row["synthesis"]),
        "finalize_result": _decode_jsonb(row["finalize_result"]),
        "conversation_ids": _decode_jsonb(row["conversation_ids"]),
        "pdf_url": row["pdf_url"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def get_or_create_draft(period_label: str, draft_slug: str = "primary") -> dict:
    """Return the existing draft for (period_label, draft_slug), creating an empty
    one if it doesn't exist yet. This is the resume path: calling start_report with
    the same period_label from a fresh chat lands on the same row."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO public.tsxv50_report_drafts (period_label, draft_slug)
                VALUES ($1, $2)
                ON CONFLICT (period_label, draft_slug) DO NOTHING
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
            )
            if row is None:
                row = await conn.fetchrow(
                    f"""
                    SELECT {_COLUMNS} FROM public.tsxv50_report_drafts
                    WHERE period_label = $1 AND draft_slug = $2
                    """,
                    period_label,
                    draft_slug,
                )
            return _row_to_dict(row)


async def get_draft(period_label: str, draft_slug: str = "primary") -> dict | None:
    """Return the draft row for (period_label, draft_slug), or None if it doesn't exist.
    Every pipeline stage calls this first, on every turn — never trust conversation
    memory for state, a same-day gap and a three-day gap must look identical."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_COLUMNS} FROM public.tsxv50_report_drafts
                WHERE period_label = $1 AND draft_slug = $2
                """,
                period_label,
                draft_slug,
            )
            return _row_to_dict(row) if row else None


async def list_drafts(period_label: str) -> list[dict]:
    """Return every draft version for a period, newest-updated first. Read-only
    discoverability — never used to auto-resolve which draft to act on; that
    choice is always an explicit draft_slug parameter."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_COLUMNS} FROM public.tsxv50_report_drafts
                WHERE period_label = $1
                ORDER BY updated_at DESC
                """,
                period_label,
            )
            return [_row_to_dict(row) for row in rows]


async def set_meta(period_label: str, draft_slug: str, meta: dict) -> dict | None:
    """Write Phase A's meta block (publication, report_title, edition_tagline,
    period_label display string, data_as_of, currency, cover_image)."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET meta = $3, updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                json.dumps(meta),
            )
            return _row_to_dict(row) if row else None


async def set_master_list(period_label: str, draft_slug: str, master_list: list[dict]) -> dict | None:
    """Write Phase A's master list (orchestrator only). Clears finalize_result and
    resets status to in_progress in the same statement -- mirrors upsert_category_content:
    a stale "locked"/"rendered" verdict must never survive a master_list edit, since a
    changed master_list can orphan category tickers (a ticker present in a category
    block but no longer in master_list) that only re-validation would catch. Found
    2026-07-28: an editorial-review master_list edit left status='rendered' and a
    passing finalize_result untouched for hours after the edit, even though the
    edited draft no longer matched what was actually rendered."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET master_list = $3, finalize_result = NULL, status = 'in_progress', updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                json.dumps(master_list),
            )
            return _row_to_dict(row) if row else None


async def set_introduction(period_label: str, draft_slug: str, introduction: dict) -> dict | None:
    """Write the whole-report introduction (finalizer, once synthesis is done)."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET introduction = $3, updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                json.dumps(introduction),
            )
            return _row_to_dict(row) if row else None


async def _merge_category_field(
    period_label: str, draft_slug: str, category: str, patch: dict, extra_set_sql: str = ""
) -> dict | None:
    """Merge `patch` into categories[category] atomically, via jsonb_set + `||`
    against the row's current value in a single statement — safe under concurrent
    per-category writes from parallel subagents, since each UPDATE is atomic
    per-row and reads the pre-update value of `categories` on its right-hand side."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET categories = jsonb_set(
                        categories,
                        ARRAY[$3],
                        COALESCE(categories -> $3, '{{}}'::jsonb) || $4::jsonb,
                        true
                    ),
                    {extra_set_sql}
                    updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                category,
                json.dumps(patch),
            )
            return _row_to_dict(row) if row else None


async def upsert_category_research(
    period_label: str, draft_slug: str, category: str, research: dict
) -> dict | None:
    """Write a category-researcher's findings for one category. Idempotent per
    category name — a re-run overwrites that category's research, leaving
    every other category's research and any already-drafted content untouched."""
    return await _merge_category_field(
        period_label,
        draft_slug,
        category,
        {"research": research, "status": "researched"},
    )


async def set_synthesis(period_label: str, draft_slug: str, synthesis: dict) -> dict | None:
    """Write the synthesist's cross-company trend/sector-comparison output.
    Runs once, after every category's research exists."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET synthesis = $3, updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                json.dumps(synthesis),
            )
            return _row_to_dict(row) if row else None


async def upsert_category_content(
    period_label: str,
    draft_slug: str,
    category: str,
    content: dict,
    sources: list[dict] | None = None,
) -> dict | None:
    """Write a category-drafter's drafted prose for one category. Idempotent per
    category name (editing an already-drafted category is the normal path, not
    an exception). Clears finalize_result and resets status to in_progress in the
    same statement — a stale "locked" verdict must never survive an edit."""
    return await _merge_category_field(
        period_label,
        draft_slug,
        category,
        {"content": content, "sources": sources or [], "status": "drafted"},
        extra_set_sql="finalize_result = NULL, status = 'in_progress',",
    )


async def set_finalize_result(period_label: str, draft_slug: str, result: dict) -> dict | None:
    """Write finalize_report's verdict. Re-runnable check, not a one-way gate:
    a passing result marks the draft 'finalized'; anything else leaves it
    'in_progress' so render_report keeps refusing to run."""
    new_status = "finalized" if result.get("status") == "pass" else "in_progress"
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET finalize_result = $3, status = $4, updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                json.dumps(result),
                new_status,
            )
            return _row_to_dict(row) if row else None


async def set_status(period_label: str, draft_slug: str, status: str) -> dict | None:
    """Set the draft's top-level status directly (e.g. 'rendered' after a
    successful render_report call). Not for 'published' — use publish() so the
    one-published-row-per-period invariant is enforced atomically."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET status = $3, updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                status,
            )
            return _row_to_dict(row) if row else None


async def set_pdf_url(period_label: str, draft_slug: str, pdf_url: str) -> dict | None:
    """Record the rendered PDF's URL and mark the draft 'rendered'."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET pdf_url = $3, status = 'rendered', updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                pdf_url,
            )
            return _row_to_dict(row) if row else None


async def publish(period_label: str, draft_slug: str) -> dict | None:
    """Atomically make (period_label, draft_slug) the published draft, demoting
    any other draft for the same period that currently holds status='published'
    back to 'rendered' first. Exactly one row per period_label may be published
    at a time, so "what did we ship" stays a single-field answer."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE public.tsxv50_report_drafts
                    SET status = 'rendered', updated_at = now()
                    WHERE period_label = $1 AND status = 'published' AND draft_slug != $2
                    """,
                    period_label,
                    draft_slug,
                )
                row = await conn.fetchrow(
                    f"""
                    UPDATE public.tsxv50_report_drafts
                    SET status = 'published', updated_at = now()
                    WHERE period_label = $1 AND draft_slug = $2
                    RETURNING {_COLUMNS}
                    """,
                    period_label,
                    draft_slug,
                )
                return _row_to_dict(row) if row else None


async def record_conversation(period_label: str, draft_slug: str, conversation_id: str) -> dict | None:
    """Append a LibreChat conversation id to the draft's audit trail. Provenance
    only, never used for lookup — chat ids change on every fresh chat, and
    fresh-chat resume is a recurring operator pattern, so keying storage to
    session identity would fragment exactly when continuity matters most."""
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE public.tsxv50_report_drafts
                SET conversation_ids = conversation_ids || $3::jsonb, updated_at = now()
                WHERE period_label = $1 AND draft_slug = $2
                RETURNING {_COLUMNS}
                """,
                period_label,
                draft_slug,
                json.dumps([conversation_id]),
            )
            return _row_to_dict(row) if row else None
