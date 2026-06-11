"""Modal app for TSXV50 report PDF generation (WeasyPrint + matplotlib).

Two surfaces over the same renderer:
- `generate_pdf` Modal function — called cross-app by the Finance MCP tool.
- `web` ASGI endpoint (POST /generate) — Bearer-authed HTTP access for the agent
  if the MCP arg path ever needs a fallback.
"""
import modal

app = modal.App("CMR-PDF")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libpango-1.0-0",
        "libpangoft2-1.0-0",
        "libharfbuzz0b",
        "libharfbuzz-subset0",
        "fonts-liberation",
    )
    .pip_install(
        "weasyprint>=62",
        "matplotlib>=3.8",
        "jinja2>=3.1",
        "pydantic>=2.9",
        "supabase>=2.10",
        "fastapi",
    )
    .add_local_python_source("src")
    .add_local_dir(
        "src/services/pdf/templates",
        remote_path="/root/src/services/pdf/templates",
    )
)

secrets = [
    modal.Secret.from_name("supabase-credentials-develop"),
    modal.Secret.from_name("app-config-develop"),
]


@app.function(image=image, timeout=300, secrets=secrets)
def generate_pdf(report_json: dict) -> dict:
    """Render + upload; returns the tool contract or a structured validation error."""
    from src.services.pdf import ReportValidationError, generate_tsxv50_pdf

    try:
        return generate_tsxv50_pdf(report_json)
    except ReportValidationError as e:
        return e.to_dict()


@app.function(image=image, timeout=300, allow_concurrent_inputs=10, secrets=secrets)
@modal.asgi_app()
def web():
    import os

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse

    from src.services.pdf import ReportValidationError, generate_tsxv50_pdf

    api = FastAPI(title="TSXV50 PDF Generator")
    token = os.environ["TSXV50_API_TOKEN"]

    @api.post("/generate")
    async def generate(request: Request) -> JSONResponse:
        if request.headers.get("Authorization") != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="Unauthorized")
        report_json = await request.json()
        try:
            return JSONResponse(content=generate_tsxv50_pdf(report_json))
        except ReportValidationError as e:
            return JSONResponse(content=e.to_dict(), status_code=422)

    return api
