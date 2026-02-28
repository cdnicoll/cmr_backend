"""Resources API router."""
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_validated_jwt_user
from src.api.schemas.resources import BatchCreateResourceRequest, BatchCreateResourceResponse
from src.models.responses import ValidatedJWTUser
from src.services.resources_service import batch_create


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
