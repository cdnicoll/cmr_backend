"""Resources service — batch create orchestration."""
from uuid import UUID

from src.api.schemas.resources import BatchCreateResourceResponse, ResourceResult
from src.utils.logging import get_logger
from src.services.supabase.resources_dao import get_resource_by_url, insert_resource
from src.utils.url_validation import validate_url


logger = get_logger(__name__)


async def batch_create(urls: list[str], request_id: str | None = None) -> BatchCreateResourceResponse:
    """
    Validate each URL, insert new resources, skip duplicates.
    Returns batch response with created/skipped/errors counts and per-URL results.
    """
    extra = {"request_id": request_id} if request_id else {}
    logger.info("batch_create started", extra=extra)
    created = 0
    skipped = 0
    errors = 0
    results: list[ResourceResult] = []

    for url in urls:
        validation = validate_url(url)
        if not validation.valid:
            errors += 1
            results.append(
                ResourceResult(
                    url=url,
                    status="error",
                    resource_id=None,
                    error=validation.error,
                )
            )
            continue

        assert validation.normalized_url is not None
        normalized_url = validation.normalized_url
        resource_type = validation.resource_type

        # Check for existing (duplicate)
        existing = await get_resource_by_url(normalized_url)
        if existing:
            skipped += 1
            results.append(
                ResourceResult(
                    url=normalized_url,
                    status="skipped",
                    resource_id=UUID(str(existing["id"])),
                    error=None,
                )
            )
            continue

        # Insert new resource
        row = await insert_resource(normalized_url, resource_type)
        if row:
            created += 1
            results.append(
                ResourceResult(
                    url=normalized_url,
                    status="created",
                    resource_id=UUID(str(row["id"])),
                    error=None,
                )
            )
        else:
            # Race: another request inserted between get and insert; treat as skipped
            existing = await get_resource_by_url(normalized_url)
            if existing:
                skipped += 1
                results.append(
                    ResourceResult(
                        url=normalized_url,
                        status="skipped",
                        resource_id=UUID(str(existing["id"])),
                        error=None,
                    )
                )
            else:
                errors += 1
                results.append(
                    ResourceResult(
                        url=normalized_url,
                        status="error",
                        resource_id=None,
                        error="Failed to insert resource",
                    )
                )

    logger.info(
        "batch_create completed: created=%d skipped=%d errors=%d",
        created,
        skipped,
        errors,
        extra=extra,
    )
    return BatchCreateResourceResponse(
        created=created,
        skipped=skipped,
        errors=errors,
        results=results,
    )
