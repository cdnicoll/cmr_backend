"""Resources API schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BatchCreateResourceRequest(BaseModel):
    """Request body for batch resource creation."""

    urls: list[str] = Field(..., min_length=1, description="1..N URLs to process")


class ResourceResult(BaseModel):
    """Per-URL result in batch response."""

    url: str
    status: Literal["created", "skipped", "error"]
    resource_id: UUID | None = None  # Present when created or skipped
    error: str | None = None  # Present when status=error


class BatchCreateResourceResponse(BaseModel):
    """Response for batch resource creation."""

    created: int
    skipped: int
    errors: int
    results: list[ResourceResult]
