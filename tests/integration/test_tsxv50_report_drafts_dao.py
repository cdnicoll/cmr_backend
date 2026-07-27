"""Integration tests for tsxv50_report_drafts_dao — round-trips a real draft row
against Postgres via asyncpg.

Skipped by default: these tests write real rows (to a `pytest-<uuid>` period_label,
cleaned up in a fixture teardown, but still real traffic against whatever database
TRANSACTION_POOLER_URL points at). Opt in explicitly once migration 009 has been
applied to a database you're comfortable writing test rows to:

    RUN_DB_INTEGRATION_TESTS=1 pytest tests/integration/test_tsxv50_report_drafts_dao.py

Plain sync test functions wrapping asyncio.run() — no pytest-asyncio dependency,
matching the rest of this project's test suite (no other test exercises the
async DAOs, so there's no existing async-test convention to follow).
"""
import asyncio
import os
import uuid

import pytest

from src.services.supabase import tsxv50_report_drafts_dao as drafts

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_DB_INTEGRATION_TESTS"),
    reason="writes real rows to Postgres; set RUN_DB_INTEGRATION_TESTS=1 to opt in",
)


@pytest.fixture()
def period_label():
    """A unique period_label per test run, so runs never collide and rows are
    easy to identify/clean up by hand if a test fails before teardown."""
    label = f"pytest-{uuid.uuid4().hex[:12]}"
    yield label
    # Best-effort cleanup: the DAO has no delete_draft (not part of the pipeline
    # contract — drafts aren't meant to be deleted by agents), so remove the row
    # directly here rather than adding a delete function nothing else needs.
    import asyncpg

    from src.models.config import load_settings

    async def _cleanup():
        conn = await asyncpg.connect(load_settings().transaction_pooler_url, statement_cache_size=0)
        try:
            await conn.execute(
                "DELETE FROM public.tsxv50_report_drafts WHERE period_label = $1", label
            )
        finally:
            await conn.close()

    asyncio.run(_cleanup())


def test_get_or_create_draft_resumes_same_row(period_label):
    """Calling start_report twice with the same (period_label, draft_slug) — the
    fresh-chat resume path — must return the same row, not create a second one."""

    async def scenario():
        first = await drafts.get_or_create_draft(period_label)
        second = await drafts.get_or_create_draft(period_label)
        return first, second

    first, second = asyncio.run(scenario())
    assert first["id"] == second["id"]
    assert first["draft_slug"] == "primary"
    assert first["status"] == "in_progress"


def test_category_edit_after_finalize_clears_finalize_result(period_label):
    """The cascade-invalidation rule: any write to a category must clear
    finalize_result and reset status to in_progress, so a stale 'locked' verdict
    can never survive an edit — the fix for the 07-26 fabricated Render Readiness
    Certificate class of bug."""

    gold_content = {
        "category": "Gold",
        "tagline": "t",
        "intro": {"sections": [{"subhead": "s", "body": "b"}]},
        "companies": [
            {
                "name": "Test Co",
                "ticker": "TEST.V",
                "table": {
                    "main_regions": "Canada",
                    "market_cap_cad_mn": 1.0,
                    "price_cad": 1.0,
                    "wk52_high_cad": 1.0,
                    "wk52_low_cad": 1.0,
                },
                "subhead": "s",
                "blurbs": {"company": "c", "recent_operations": "r", "finances": "f", "outlook": "o"},
            }
        ],
    }

    async def scenario():
        await drafts.get_or_create_draft(period_label)
        await drafts.set_meta(
            period_label,
            "primary",
            {
                "publication": "Canadian Mining Report",
                "report_title": "TSXV Top 50 Metal Miners",
                "edition_tagline": "Test Edition",
                "period_label": "Test Period",
                "data_as_of": "2026-01-01",
            },
        )
        await drafts.set_master_list(
            period_label,
            "primary",
            [{"rank": 1, "company": "Test Co", "ticker": "TEST.V", "category": "Gold", "market_cap_cad_mn": 1.0}],
        )
        await drafts.set_introduction(period_label, "primary", {"sections": [{"subhead": "s", "body": "b"}]})
        await drafts.upsert_category_content(period_label, "primary", "Gold", gold_content)

        # Manually simulate finalize_report's write (schema.py has heavy import
        # deps not needed for this DAO-focused test).
        await drafts.set_finalize_result(period_label, "primary", {"status": "pass", "checked_at": "now"})
        finalized = await drafts.get_draft(period_label, "primary")

        # Edit the same category again — this must clear finalize_result and drop
        # status back to in_progress, even though nothing else changed.
        await drafts.upsert_category_content(
            period_label,
            "primary",
            "Gold",
            {**gold_content, "tagline": "revised tagline"},
        )
        after_edit = await drafts.get_draft(period_label, "primary")
        return finalized, after_edit

    finalized, after_edit = asyncio.run(scenario())
    assert finalized["status"] == "finalized"
    assert finalized["finalize_result"]["status"] == "pass"
    assert after_edit["status"] == "in_progress"
    assert after_edit["finalize_result"] is None
    assert after_edit["categories"]["Gold"]["content"]["tagline"] == "revised tagline"


def test_parallel_category_writes_do_not_clobber_each_other(period_label):
    """Two categories written concurrently must both land — this is the whole
    point of the jsonb_set-against-current-value approach over a client-side
    read-modify-write, since parallel category-researcher/category-drafter
    subagents write to different keys of the same row."""

    async def scenario():
        await drafts.get_or_create_draft(period_label)
        await asyncio.gather(
            drafts.upsert_category_research(period_label, "primary", "Gold", {"story": "gold story"}),
            drafts.upsert_category_research(period_label, "primary", "Silver", {"story": "silver story"}),
            drafts.upsert_category_research(period_label, "primary", "Lithium", {"story": "lithium story"}),
        )
        return await drafts.get_draft(period_label, "primary")

    draft = asyncio.run(scenario())
    assert set(draft["categories"].keys()) == {"Gold", "Silver", "Lithium"}
    assert draft["categories"]["Gold"]["research"]["story"] == "gold story"
    assert draft["categories"]["Silver"]["research"]["story"] == "silver story"
    assert draft["categories"]["Lithium"]["research"]["story"] == "lithium story"


def test_publish_demotes_previously_published_draft(period_label):
    """Exactly one row per period_label may hold status='published' at a time."""

    async def scenario():
        await drafts.get_or_create_draft(period_label, "primary")
        await drafts.get_or_create_draft(period_label, "editorial-a")

        await drafts.publish(period_label, "primary")
        first = await drafts.get_draft(period_label, "primary")

        await drafts.publish(period_label, "editorial-a")
        first_after = await drafts.get_draft(period_label, "primary")
        second = await drafts.get_draft(period_label, "editorial-a")
        return first, first_after, second

    first, first_after, second = asyncio.run(scenario())
    assert first["status"] == "published"
    assert first_after["status"] == "rendered"  # demoted, not deleted
    assert second["status"] == "published"


def test_list_drafts_returns_every_version(period_label):
    async def scenario():
        await drafts.get_or_create_draft(period_label, "primary")
        await drafts.get_or_create_draft(period_label, "editorial-a")
        await drafts.get_or_create_draft(period_label, "editorial-b")
        return await drafts.list_drafts(period_label)

    versions = asyncio.run(scenario())
    assert {v["draft_slug"] for v in versions} == {"primary", "editorial-a", "editorial-b"}
