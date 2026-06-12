"""Render a validated TSXV50 report to HTML and PDF (WeasyPrint)."""
import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.services.pdf.charts import render_chart_svg
from src.services.pdf.schema import SECTOR_ORDER, MasterListEntry, Report, validate_report

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class RenderedReport:
    pdf_bytes: bytes
    page_count: int
    filename: str


def _money(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "–"
    return f"{value:,.1f}%"


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
    )
    env.filters["money"] = _money
    env.filters["pct"] = _pct
    return env


def period_slug(period_label: str) -> str:
    """'Q2 2026' -> 'q2-2026' (used in the output filename)."""
    return re.sub(r"[^a-z0-9]+", "-", period_label.lower()).strip("-")


def _master_columns(entries: list[MasterListEntry]) -> list[list[dict]]:
    """Group the master list into sector blocks (spec order, ranked within), then
    split the blocks into two balanced columns: left fills first, like the reference."""
    sectors = []
    for name in SECTOR_ORDER:
        block = sorted(
            (e for e in entries if e.category == name), key=lambda e: e.rank
        )
        if block:
            sectors.append({"name": name, "entries": block})

    # Balance by rendered height: each sector costs a header (~2 rows) + its rows.
    weights = [len(s["entries"]) + 2 for s in sectors]
    total = sum(weights)
    left: list[dict] = []
    acc = 0
    for sector, weight in zip(sectors, weights):
        if acc < total / 2 or not left:
            left.append(sector)
            acc += weight
        else:
            break
    right = sectors[len(left) :]
    return [left, right] if right else [left]


def render_html(report: Report) -> str:
    """Render the full report HTML with charts pre-rendered to inline SVG."""
    chart_svgs = [
        render_chart_svg(cat.chart) if cat.chart else None for cat in report.categories
    ]

    # Figure 1 is the master table; category charts continue the numbering.
    figure_numbers: list[int | None] = []
    next_figure = 2
    for cat in report.categories:
        if cat.chart:
            figure_numbers.append(next_figure)
            next_figure += 1
        else:
            figure_numbers.append(None)

    # P/B + Upside columns are hidden only when null across the whole edition.
    show_ratio_columns = any(
        co.table.pb is not None or co.table.upside_to_target_pct is not None
        for cat in report.categories
        for co in cat.companies
    )

    env = _build_env()
    return env.get_template("report.html.j2").render(
        report=report,
        master_columns=_master_columns(report.master_list),
        chart_svgs=chart_svgs,
        figure_numbers=figure_numbers,
        show_ratio_columns=show_ratio_columns,
        footer_text=(
            f"© {report.meta.data_as_of.year} {report.meta.publication}. "
            "All rights reserved."
        ),
    )


def render_pdf(report_json: dict) -> RenderedReport:
    """Validate report_json and render the PDF. Raises ReportValidationError on bad input."""
    # Imported here so schema/HTML paths work without WeasyPrint's native libs.
    import weasyprint

    report = validate_report(report_json)
    html = render_html(report)
    document = weasyprint.HTML(string=html, base_url=str(TEMPLATE_DIR)).render()
    return RenderedReport(
        pdf_bytes=document.write_pdf(),
        page_count=len(document.pages),
        filename=f"tsxv50-{period_slug(report.meta.period_label)}.pdf",
    )
