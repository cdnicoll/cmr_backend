"""Supabase Storage upload for rendered TSXV50 PDFs."""
import os

from supabase import create_client

BUCKET = "tsxv50-reports"
SIGNED_URL_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days — covers the edition send window


def upload_pdf(pdf_bytes: bytes, filename: str) -> str:
    """Upload to the tsxv50-reports bucket (upsert) and return a signed URL."""
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    storage = client.storage

    try:
        storage.create_bucket(BUCKET, options={"public": False})
    except Exception:
        pass  # already exists

    storage.from_(BUCKET).upload(
        filename,
        pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    signed = storage.from_(BUCKET).create_signed_url(filename, SIGNED_URL_TTL_SECONDS)
    if isinstance(signed, dict):
        url = signed.get("signedURL") or signed.get("signed_url")
        if url:
            return url
    raise RuntimeError(f"Unexpected create_signed_url response: {signed!r}")
