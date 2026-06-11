"""Render the sample TSXV50 report locally — layout iteration without Modal or an agent.

Usage (macOS needs the homebrew lib path for WeasyPrint):
    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
        uv run python scripts/render_sample_pdf.py [report.json]

Writes the HTML and PDF next to the spec in _local/pdf-generation/out/.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.services.pdf import render_html, render_pdf, validate_report  # noqa: E402


def main() -> None:
    source = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else REPO_ROOT / "src/services/pdf/sample_report.json"
    )
    report_json = json.loads(source.read_text())

    out_dir = REPO_ROOT / "_local/pdf-generation/out"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = validate_report(report_json)
    html_path = out_dir / "report.html"
    html_path.write_text(render_html(report))
    print(f"HTML: {html_path}")

    rendered = render_pdf(report_json)
    pdf_path = out_dir / rendered.filename
    pdf_path.write_bytes(rendered.pdf_bytes)
    print(f"PDF:  {pdf_path}  ({rendered.page_count} pages, {len(rendered.pdf_bytes):,} bytes)")


if __name__ == "__main__":
    main()
