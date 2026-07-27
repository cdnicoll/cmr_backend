"""TSXV50 report PDF generation — pure rendering, no data fetching or model calls.

Contract: _local/pdf-generation/2026-06-11-tsxv50-pdf-tool-build-spec.md
"""
from src.services.pdf.schema import Report, ReportValidationError, validate_report

_RENDERER_EXPORTS = {"RenderedReport", "render_html", "render_pdf"}


def __getattr__(name: str):
    """Lazily resolve renderer-only exports. `renderer`/`charts` pull in
    weasyprint/matplotlib, which aren't installed everywhere that only needs
    schema validation (e.g. the Finance MCP's lightweight Modal image, which
    calls validate_report but never renders). Keeping this import lazy lets
    `from src.services.pdf import validate_report` succeed there without those
    deps present."""
    if name in _RENDERER_EXPORTS:
        from src.services.pdf import renderer

        return getattr(renderer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def generate_tsxv50_pdf(report_json: dict) -> dict:
    """Render report_json to PDF, upload to Supabase Storage, return the tool contract.

    Returns {"pdf_url", "filename", "bytes", "page_count"}.
    Raises ReportValidationError when report_json fails the schema.
    """
    from src.services.pdf.renderer import render_pdf
    from src.services.pdf.storage import upload_pdf

    rendered = render_pdf(report_json)
    pdf_url = upload_pdf(rendered.pdf_bytes, rendered.filename)
    return {
        "pdf_url": pdf_url,
        "filename": rendered.filename,
        "bytes": len(rendered.pdf_bytes),
        "page_count": rendered.page_count,
    }


__all__ = [
    "RenderedReport",
    "Report",
    "ReportValidationError",
    "generate_tsxv50_pdf",
    "render_html",
    "render_pdf",
    "validate_report",
]
