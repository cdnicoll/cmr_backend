"""Unit tests for the TSXV50 PDF rendering pipeline (schema, charts, HTML, PDF)."""
import copy
import json
from pathlib import Path

import pytest
from src.services.pdf import render_html, validate_report
from src.services.pdf.charts import render_chart_svg
from src.services.pdf.renderer import period_slug
from src.services.pdf.schema import ReportValidationError

SAMPLE_PATH = Path(__file__).resolve().parents[2] / "src/services/pdf/sample_report.json"


@pytest.fixture()
def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


def test_sample_report_validates(sample):
    report = validate_report(sample)
    assert report.meta.period_label == "Q2 2026"
    assert report.categories[0].companies[1].table.pb is None


def test_missing_required_field_rejected(sample):
    bad = copy.deepcopy(sample)
    del bad["meta"]["report_title"]
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any(i["path"] == "meta.report_title" for i in exc.value.issues)


def test_bad_category_enum_rejected(sample):
    bad = copy.deepcopy(sample)
    bad["master_list"][0]["category"] = "Tin"
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any(i["path"].startswith("master_list.0.category") for i in exc.value.issues)


def test_non_numeric_table_value_rejected(sample):
    bad = copy.deepcopy(sample)
    bad["categories"][0]["companies"][0]["table"]["price_cad"] = "n/a"
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any("price_cad" in i["path"] for i in exc.value.issues)


def test_non_dict_payload_rejected():
    with pytest.raises(ReportValidationError):
        validate_report("not a dict")  # type: ignore[arg-type]


def test_period_slug():
    assert period_slug("Q2 2026") == "q2-2026"


def test_chart_renders_svg(sample):
    report = validate_report(sample)
    svg = render_chart_svg(report.categories[0].chart)
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_render_html_layout(sample):
    html = render_html(validate_report(sample))
    assert "1911 Gold Corporation (AUMB.V)" in html
    assert "Golden Times" in html
    # Sample has one company with P/B set, so ratio columns are shown
    assert "P/B" in html and "Upside to Target" in html
    # Master list figure + gold chart figure numbering
    assert "Figure 1: TSXV Top 50 Miners by Sector" in html
    assert "Figure 2: Gold Price Performance" in html
    assert "<svg" in html


def test_render_html_hides_ratio_columns_when_all_null(sample):
    edition = copy.deepcopy(sample)
    for company in edition["categories"][0]["companies"]:
        company["table"]["pb"] = None
        company["table"]["upside_to_target_pct"] = None
    html = render_html(validate_report(edition))
    assert "<th>P/B</th>" not in html
    assert "<th>Upside to Target</th>" not in html


def test_limited_activity_renders(sample):
    edition = copy.deepcopy(sample)
    edition["categories"][0]["limited_activity"] = [
        {
            "name": "Quiet Gold Corp",
            "ticker": "QGC.V",
            "note": "No press releases issued this period; the fully funded Phase 2 drill program remains scheduled for Q3.",
        }
    ]
    edition["master_list"].append(
        {"rank": 3, "company": "Quiet Gold Corp", "ticker": "QGC.V", "category": "Gold", "market_cap_cad_mn": 50.0}
    )
    html = render_html(validate_report(edition))
    assert "Companies with Limited Activity This Period" in html
    assert "Quiet Gold Corp (QGC.V)" in html


def test_limited_activity_absent_by_default(sample):
    html = render_html(validate_report(sample))
    assert "Companies with Limited Activity" not in html


def test_category_with_only_limited_activity_validates(sample):
    edition = copy.deepcopy(sample)
    edition["categories"][0]["companies"] = []
    edition["categories"][0]["limited_activity"] = [
        {"name": "Quiet Gold Corp", "ticker": "QGC.V", "note": "Quiet period."}
    ]
    # companies was cleared, so master_list must only carry the one remaining
    # (now limited-activity) entry, or the completeness check rejects the
    # dropped AUMB.V/OMG.V rows as orphaned.
    edition["master_list"] = [
        {"rank": 1, "company": "Quiet Gold Corp", "ticker": "QGC.V", "category": "Gold", "market_cap_cad_mn": 50.0}
    ]
    report = validate_report(edition)
    assert report.categories[0].companies == []
    assert report.categories[0].limited_activity[0].ticker == "QGC.V"


def test_category_with_no_companies_or_limited_activity_rejected(sample):
    bad = copy.deepcopy(sample)
    bad["categories"][0]["companies"] = []
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any(i["path"].startswith("categories.0") for i in exc.value.issues)


# --- Report-level completeness validator (issue #2) ---
# Closes the 2026-07-26 truncated-payload gap: a partial payload (missing
# categories, duplicate tail rows) must fail here instead of rendering a
# confident wrong PDF.


def test_duplicate_master_list_ticker_rejected(sample):
    bad = copy.deepcopy(sample)
    bad["master_list"].append(dict(bad["master_list"][0]))
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any("duplicate ticker(s) in master_list" in i["message"] for i in exc.value.issues)


def test_orphaned_master_list_entry_rejected(sample):
    """A master_list row with no matching company/limited_activity entry anywhere
    in categories — the exact shape of the 07-26 truncated-payload failure, where
    the master list outran what the categories actually contained."""
    bad = copy.deepcopy(sample)
    bad["master_list"].append(
        {"rank": 3, "company": "Ghost Co", "ticker": "GHOST.V", "category": "Gold", "market_cap_cad_mn": 1.0}
    )
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any("GHOST.V" in i["message"] for i in exc.value.issues)


def test_unclassified_master_list_row_needs_no_category_entry(sample):
    """Unclassified rows are master-list-only by contract (issue #19): a
    non-mining constituent keeps its rank with no category section, and the
    completeness check must not flag it as orphaned."""
    edition = copy.deepcopy(sample)
    edition["master_list"].append(
        {"rank": 3, "company": "Non Mining Co", "ticker": "NMC.V", "category": "Unclassified", "market_cap_cad_mn": 1.0}
    )
    report = validate_report(edition)
    assert {m.ticker for m in report.master_list} == {"AUMB.V", "OMG.V", "NMC.V"}


def test_unclassified_master_list_row_still_subject_to_other_checks(sample):
    """The exemption is only from the orphan check — a duplicated Unclassified
    ticker or a rank gap must still fail."""
    bad = copy.deepcopy(sample)
    bad["master_list"].append(
        {"rank": 3, "company": "Non Mining Co", "ticker": "NMC.V", "category": "Unclassified", "market_cap_cad_mn": 1.0}
    )
    bad["master_list"].append(
        {"rank": 5, "company": "Non Mining Co", "ticker": "NMC.V", "category": "Unclassified", "market_cap_cad_mn": 1.0}
    )
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    messages = [i["message"] for i in exc.value.issues]
    assert any("duplicate ticker(s) in master_list" in m for m in messages)
    assert any("contiguous" in m for m in messages)


def test_orphaned_category_entry_rejected(sample):
    """A category has a company with no corresponding master_list row."""
    bad = copy.deepcopy(sample)
    ghost_company = copy.deepcopy(bad["categories"][0]["companies"][0])
    ghost_company["name"] = "Ghost Co"
    ghost_company["ticker"] = "GHOST2.V"
    bad["categories"][0]["companies"].append(ghost_company)
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any("GHOST2.V" in i["message"] for i in exc.value.issues)


def test_non_contiguous_ranks_rejected(sample):
    bad = copy.deepcopy(sample)
    bad["master_list"][1]["rank"] = 5
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any("contiguous" in i["message"] for i in exc.value.issues)


def test_duplicate_ticker_across_categories_rejected(sample):
    """The 07-26 degradation signature: a duplicate company row appended near
    the end of a category's companies list."""
    bad = copy.deepcopy(sample)
    bad["categories"][0]["companies"].append(dict(bad["categories"][0]["companies"][0]))
    with pytest.raises(ReportValidationError) as exc:
        validate_report(bad)
    assert any("duplicate ticker(s) across categories" in i["message"] for i in exc.value.issues)


def test_valid_report_passes_completeness_check(sample):
    """The fixture itself must be internally consistent — every master_list
    ticker matches exactly one category entry and ranks are contiguous."""
    report = validate_report(sample)
    assert len(report.master_list) == 2
    assert {m.ticker for m in report.master_list} == {"AUMB.V", "OMG.V"}


def _full_edition(sample: dict) -> dict:
    """Synthesize a full 51-company edition from the sample to stress page-break behavior."""
    edition = copy.deepcopy(sample)
    gold = edition["categories"][0]
    sectors = [
        "Gold", "Copper & Base Metals", "Royalty & Streaming", "Silver", "Lithium", "Uranium"
    ]

    edition["master_list"] = []
    edition["categories"] = []
    rank = 1
    for s_idx, sector in enumerate(sectors):
        cat = copy.deepcopy(gold)
        cat["category"] = sector
        cat["companies"] = []
        for i in range(9 if s_idx < 3 else 8):
            company = copy.deepcopy(gold["companies"][i % 2])
            company["name"] = f"{sector} Test Co {i + 1}"
            company["ticker"] = f"T{s_idx}{i}.V"
            cat["companies"].append(company)
            edition["master_list"].append(
                {
                    "rank": rank,
                    "company": company["name"],
                    "ticker": company["ticker"],
                    "category": sector,
                    "market_cap_cad_mn": 500.0 - rank * 7.3,
                }
            )
            rank += 1
        edition["categories"].append(cat)
    return edition


def test_render_pdf_full_pipeline(sample):
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError) as e:
        # WeasyPrint needs pango at import time; on macOS run tests with
        # DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib to include this test.
        pytest.skip(f"weasyprint unavailable: {e}")
    from src.services.pdf import render_pdf

    rendered = render_pdf(sample)
    assert rendered.pdf_bytes.startswith(b"%PDF")
    assert rendered.page_count >= 3
    assert rendered.filename == "tsxv50-q2-2026.pdf"


def test_render_pdf_full_51_company_edition(sample):
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError) as e:
        pytest.skip(f"weasyprint unavailable: {e}")
    from src.services.pdf import render_pdf

    edition = _full_edition(sample)
    assert len(edition["master_list"]) == 51
    rendered = render_pdf(edition)
    assert rendered.pdf_bytes.startswith(b"%PDF")
    # 6 category sections of 8-9 companies each: well past the single-category sample
    assert rendered.page_count >= 12
