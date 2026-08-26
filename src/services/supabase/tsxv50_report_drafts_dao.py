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


def _jsonb_chars(value) -> int:
    """Rough serialized size of one stored block, for the baseline index. Lets a
    caller decide how many categories to pull per turn instead of discovering the
    payload ceiling the hard way (2026-07-26)."""
    if value is None:
        return 0
    return len(value if isinstance(value, str) else json.dumps(value, default=str))


def _category_index_entry(block) -> dict:
    """One line of the baseline's per-category index: what state that category is in
    and how big its stored blocks are, without returning either block."""
    if not isinstance(block, dict):
        return {"status": None, "updated_at": None, "research_chars": 0, "content_chars": 0}
    return {
        "status": block.get("status"),
        "updated_at": block.get("updated_at"),
        "research_chars": _jsonb_chars(block.get("research")),
        "content_chars": _jsonb_chars(block.get("content")),
    }


async def list_periods() -> list[dict]:
    """Index every draft across every period, newest-updated first.

    Deliberately lightweight: no meta, master_list, categories or research payload
    crosses this boundary, only enough to recognize an edition. The whole point of
    this read is finding a *previous* edition to build a follow-up against, and
    returning full rows to do it would walk straight back into the payload ceiling
    that the draft store exists to avoid.

    Read-only discoverability, same contract as list_drafts: never used to
    auto-resolve which draft to act on. Which edition is the baseline is always an
    explicit parameter, chosen by the operator.
    """
    db_url = load_settings().transaction_pooler_url
    async with asyncpg.create_pool(
        db_url, min_size=1, max_size=5, statement_cache_size=0
    ) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    d.period_label,
                    d.draft_slug,
                    d.status,
                    d.meta->>'period_label' AS period_display,
                    d.meta->>'data_as_of'   AS data_as_of,
                    CASE
                        WHEN jsonb_typeof(d.master_list) = 'array'
                        THEN jsonb_array_length(d.master_list)
                        ELSE 0
                    END AS company_count,
                    CASE
                        WHEN jsonb_typeof(d.categories) = 'object'
                        THEN (SELECT count(*) FROM jsonb_object_keys(d.categories))
                        ELSE 0
                    END AS category_count,
                    d.pdf_url IS NOT NULL AS has_pdf,
                    d.updated_at
                FROM public.tsxv50_report_drafts d
                ORDER BY d.updated_at DESC
                """
            )
            return [
                {
                    "period_label": row["period_label"],
                    "draft_slug": row["draft_slug"],
                    "status": row["status"],
                    "period_display": row["period_display"],
                    "data_as_of": row["data_as_of"],
                    "company_count": row["company_count"],
                    "category_count": row["category_count"],
                    "has_pdf": row["has_pdf"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]


async def get_baseline(
    period_label: str, draft_slug: str = "primary", category: str | None = None
) -> dict | None:
    """Read a previous edition as the baseline for a follow-up, without dragging its
    drafted prose along.

    Without `category`: the edition's meta, master_list and synthesis, plus a
    per-category index (status, timestamp, block sizes) so a caller can see what is
    there and pull research in batches.

    With `category`: only that category's stored research — the current-story blocks,
    statuses and next-expected-catalyst dates a follow-up reports movement against.

    Drafted prose (`content`) is never returned in either mode. A follow-up
    re-verifies and re-states; it does not copy the last edition's sentences.

    Returns None when the draft doesn't exist. An unknown category comes back with
    `category_found: False` plus the categories that do exist, rather than an empty
    result a caller could read as "that category had no research".

    Deliberately shape-agnostic about what is inside `research`: that jsonb is
    authored by the category-researcher against a prose contract in
    `agents/category-researcher.md`, not a schema this module owns, so nothing here
    reaches into its keys.
    """
    draft = await get_draft(period_label, draft_slug)
    if draft is None:
        return None

    categories = draft.get("categories")
    if not isinstance(categories, dict):
        categories = {}

    if category is not None:
        block = categories.get(category)
        if not isinstance(block, dict):
            return {
                "period_label": draft["period_label"],
                "draft_slug": draft["draft_slug"],
                "category": category,
                "category_found": False,
                "available_categories": sorted(categories),
                "research": None,
            }
        return {
            "period_label": draft["period_label"],
            "draft_slug": draft["draft_slug"],
            "category": category,
            "category_found": True,
            "status": block.get("status"),
            "updated_at": block.get("updated_at"),
            "research": block.get("research"),
        }

    return {
        "period_label": draft["period_label"],
        "draft_slug": draft["draft_slug"],
        "status": draft["status"],
        "meta": draft["meta"],
        "master_list": draft["master_list"],
        "synthesis": draft["synthesis"],
        "pdf_url": draft["pdf_url"],
        "updated_at": draft["updated_at"],
        "categories": {name: _category_index_entry(block) for name, block in categories.items()},
    }


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
