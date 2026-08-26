"""Unit tests for get_baseline's filtering — the read a follow-up report builds on.

No database: get_draft is monkeypatched, because what's under test is the shape of
what crosses the tool boundary, not the query. Two properties matter and both are
load-bearing for the monthly update flow:

1. Drafted prose never comes back. A follow-up re-verifies and re-states; if last
   edition's sentences were available they would get reused, and stale-but-valid
   text is exactly the failure mode of known gaps 10 and 12 (schema-valid, wrong).
2. A whole edition never has to be pulled in one turn. The per-category index
   reports block sizes so the caller can batch, which is the 2026-07-26 payload
   ceiling lesson applied to reads instead of writes.
"""
import asyncio
import json

from src.services.supabase import tsxv50_report_drafts_dao as drafts

PROSE = "Talamore advanced its Silver Surfer program through the quarter."

DRAFT = {
    "id": 7,
    "period_label": "2026-Q2",
    "draft_slug": "primary",
    "status": "published",
    "meta": {"period_label": "Q2 2026", "data_as_of": "2026-07-28"},
    "master_list": [
        {"rank": 1, "company": "Santacruz Silver", "ticker": "SCZ.V", "market_cap_cad_mn": 840.2},
        {"rank": 2, "company": "Talamore Mining", "ticker": "TALA.V", "market_cap_cad_mn": 612.0},
    ],
    "introduction": {"sections": [{"subhead": "Overview", "body": PROSE}]},
    "categories": {
        "Gold": {
            "status": "drafted",
            "updated_at": "2026-07-28T22:00:00Z",
            "research": {
                "TALA.V": {
                    "current_story": {
                        "story": "Silver Surfer permitting",
                        "status": "advanced",
                        "next_expected_catalyst": "permit decision, Q4 2026",
                    }
                }
            },
            "content": {"companies": [{"ticker": "TALA.V", "blurbs": {"outlook": PROSE}}]},
        },
        "Silver": {
            "status": "researched",
            "updated_at": "2026-07-27T10:00:00Z",
            "research": {
                "SCZ.V": {"current_story": {"story": "Bolivia restart", "status": "stalled"}}
            },
            "content": None,
        },
    },
    "synthesis": {"trends": ["financing reopened for developers"]},
    "finalize_result": {"ok": True},
    "conversation_ids": ["abc"],
    "pdf_url": "https://example.invalid/tsxv50-q2-2026.pdf",
    "created_at": "2026-07-20T00:00:00Z",
    "updated_at": "2026-07-30T00:00:00Z",
}


def _patch_get_draft(monkeypatch, draft=DRAFT):
    async def fake_get_draft(period_label, draft_slug="primary"):
        return draft

    monkeypatch.setattr(drafts, "get_draft", fake_get_draft)


def test_baseline_index_never_returns_drafted_prose(monkeypatch):
    _patch_get_draft(monkeypatch)
    result = asyncio.run(drafts.get_baseline("2026-Q2"))

    assert PROSE not in json.dumps(result), "drafted prose must not cross the baseline boundary"
    assert result["master_list"][0]["ticker"] == "SCZ.V"
    assert result["synthesis"] == {"trends": ["financing reopened for developers"]}
    assert set(result["categories"]) == {"Gold", "Silver"}


def test_baseline_index_reports_block_sizes_for_batching(monkeypatch):
    _patch_get_draft(monkeypatch)
    result = asyncio.run(drafts.get_baseline("2026-Q2"))

    gold = result["categories"]["Gold"]
    assert gold["status"] == "drafted"
    assert gold["research_chars"] > 0
    assert gold["content_chars"] > 0
    # A category researched but not yet drafted reports zero for content, not None:
    # the caller is sizing a payload, and None doesn't add up.
    assert result["categories"]["Silver"]["content_chars"] == 0


def test_baseline_for_one_category_returns_research_only(monkeypatch):
    _patch_get_draft(monkeypatch)
    result = asyncio.run(drafts.get_baseline("2026-Q2", category="Gold"))

    assert result["category_found"] is True
    assert result["research"]["TALA.V"]["current_story"]["status"] == "advanced"
    assert PROSE not in json.dumps(result)
    assert "content" not in result


def test_unknown_category_is_distinguishable_from_empty_research(monkeypatch):
    """An unknown category must not look like a category that was researched and
    found nothing — that ambiguity is how "no material change" gets published about
    a company nobody actually looked at."""
    _patch_get_draft(monkeypatch)
    result = asyncio.run(drafts.get_baseline("2026-Q2", category="Uranium"))

    assert result["category_found"] is False
    assert result["research"] is None
    assert result["available_categories"] == ["Gold", "Silver"]


def test_missing_draft_returns_none(monkeypatch):
    async def fake_get_draft(period_label, draft_slug="primary"):
        return None

    monkeypatch.setattr(drafts, "get_draft", fake_get_draft)
    assert asyncio.run(drafts.get_baseline("2026-Q9")) is None


def test_malformed_category_block_does_not_crash_the_index(monkeypatch):
    """categories is agent-written jsonb; a non-object value there must degrade to a
    zeroed index row rather than taking down the whole baseline read."""
    _patch_get_draft(monkeypatch, {**DRAFT, "categories": {"Gold": "not-an-object"}})
    result = asyncio.run(drafts.get_baseline("2026-Q2"))

    assert result["categories"]["Gold"] == {
        "status": None,
        "updated_at": None,
        "research_chars": 0,
        "content_chars": 0,
    }


def test_find_baseline_company_crosses_category_boundaries(monkeypatch):
    """A recategorized company's story lives under its OLD category. Reading only the
    new category makes a live story look like no story, which is the Vizsla failure
    shape. Seeded from the real 2026-Q2 draft, where TALA.V's research sits in the
    Copper & Base Metals block while the company is Gold in the August master list."""
    draft = {
        **DRAFT,
        "categories": {
            "Copper & Base Metals": {
                "status": "drafted",
                "research": {
                    # Note the key: this block spells it "symbol", while the Gold block
                    # below spells it "ticker". Both spellings exist in the real edition.
                    "companies": [{"symbol": "TALA.V", "current_story": {"status": "advanced"}}]
                },
                "content": {"prose": PROSE},
            },
            "Gold": {
                "status": "drafted",
                "research": {"companies": [{"ticker": "AAA.V"}]},
                "content": None,
            },
        },
    }
    _patch_get_draft(monkeypatch, draft)

    hit = asyncio.run(drafts.find_baseline_company("2026-Q2", "TALA.V"))
    assert hit["found"] is True
    assert hit["found_in_category"] == "Copper & Base Metals"
    assert hit["research"]["current_story"]["status"] == "advanced"

    # Case-insensitive, and the other spelling resolves too.
    assert asyncio.run(drafts.find_baseline_company("2026-Q2", "aaa.v"))["found"] is True


def test_find_baseline_company_distinguishes_absent_from_misfiled(monkeypatch):
    """found: false must mean "genuinely not covered last edition", never "looked in
    the wrong place" — only the former justifies treating a company as new coverage."""
    _patch_get_draft(monkeypatch)
    miss = asyncio.run(drafts.find_baseline_company("2026-Q2", "ZZZ.V"))
    assert miss["found"] is False
    assert miss["research"] is None
    assert miss["searched_categories"] == ["Gold", "Silver"]


def test_category_writes_reject_an_unknown_name():
    """jsonb_set creates a key for any string, so an escaped or misspelled category
    silently forks a phantom block. On 2026-08-25 a caller passed the ampersand
    HTML-escaped and the draft held both "Copper & Base Metals" and
    "Copper &amp; Base Metals" with the same two companies — invisible until
    finalize_report reported them as duplicate tickers, a symptom far from its cause."""
    import pytest

    from src.services.supabase.tsxv50_report_drafts_dao import (
        InvalidCategoryError,
        _validate_category,
    )

    _validate_category("Copper & Base Metals")  # literal ampersand: fine

    with pytest.raises(InvalidCategoryError) as caught:
        _validate_category("Copper &amp; Base Metals")
    assert "Copper & Base Metals" in caught.value.valid
    assert "HTML-escaped" in str(caught.value)

    for bad in ("gold", "Gold ", "Precious Metals", ""):
        with pytest.raises(InvalidCategoryError):
            _validate_category(bad)
