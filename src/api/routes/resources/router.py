"""Resources API router."""
import json
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_validated_jwt_user
from src.api.schemas.resources import BatchCreateResourceRequest, BatchCreateResourceResponse
from src.models.responses import ValidatedJWTUser
from src.services.resources_service import batch_create
from src.services.supabase.resources_dao import get_resource_by_id, requeue_resource


router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("", response_model=BatchCreateResourceResponse)
async def create_resources_batch(
    request: BatchCreateResourceRequest,
    http_request: Request,
    current_user: ValidatedJWTUser = Depends(get_validated_jwt_user),
) -> JSONResponse:
    """
    Batch create resources from URLs.
    Validates each URL (SSRF, format, type). Duplicates are skipped.
    Returns 201 if any created, 200 if all skipped.
    """
    request_id = getattr(http_request.state, "request_id", None)
    response = await batch_create(request.urls, request_id=request_id)

    status_code = status.HTTP_201_CREATED if response.created > 0 else status.HTTP_200_OK
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=status_code,
    )


@router.post("/{resource_id}/requeue")
async def requeue_resource_endpoint(
    resource_id: str,
    current_user: ValidatedJWTUser = Depends(get_validated_jwt_user),
) -> JSONResponse:
    """
    Reset a failed resource to discovered so it re-enters the pipeline.
    Returns 200 with updated resource or 404 if not found.
    """
    updated = await requeue_resource(resource_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    resource = await get_resource_by_id(resource_id)
    # Serialize for JSON (asyncpg returns datetime, UUID)
    payload = json.loads(
        json.dumps(
            resource,
            default=lambda x: x.isoformat() if isinstance(x, (datetime, date)) else str(x) if isinstance(x, UUID) else x,
        )
    )
    return JSONResponse(content=payload, status_code=status.HTTP_200_OK)
