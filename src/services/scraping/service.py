"""Scraping service — orchestrates fetch, extraction, and resource updates."""

from datetime import UTC, datetime

from src.models.config import load_settings
from src.models.resources import PipelineStage
from src.models.scraping import ScrapedContent, ScrapedContentMetadata
from src.services.scraping import crawl4ai_client, youtube_extractor
from src.services.supabase.resources_dao import (
    atomic_transition_to_scraping,
    get_resource_by_id,
    update_resource_after_scrape,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def scrape_resource(resource_id: str) -> None:
    """
    Scrape a resource by ID.
    Fetches resource, routes by type (website/youtube), extracts content,
    validates word count, updates pipeline_stage and scraped_content/failure_reason.
    """
    settings = load_settings()
    min_word_count = settings.scrape_min_word_count
    proxy_url = settings.scraping_proxy_url
    logger.info("Proxy configured: %s", "yes" if proxy_url else "no")

    # 1. Fetch resource
    resource = await get_resource_by_id(resource_id)
    if not resource:
        logger.warning("Resource not found", extra={"resource_id": resource_id})
        return

    url = resource.get("url") or ""
    resource_type = resource.get("type") or "website"
    current_stage = resource.get("pipeline_stage") or ""

    # 2. Eligibility check — skip if not discovered
    if current_stage != PipelineStage.DISCOVERED.value:
        logger.info(
            "Skipping resource %s: not in discovered stage (current: %s)",
            resource_id,
            current_stage,
            extra={"resource_id": resource_id, "pipeline_stage": current_stage},
        )
        return

    # 3. Atomic transition to scraping
    rows_updated = await atomic_transition_to_scraping(resource_id)
    if rows_updated == 0:
        logger.info(
            "Resource already claimed by another worker",
            extra={"resource_id": resource_id},
        )
        return

    logger.info(
        "Started scraping",
        extra={"resource_id": resource_id, "url": url, "type": resource_type},
    )

    try:
        # 4. Extract content by type
        if resource_type == "youtube":
            markdown, title = await _run_async(youtube_extractor.fetch_youtube_transcript, url, proxy_url)
        else:
            markdown, title = await crawl4ai_client.fetch_website_content(url, proxy_url)

        # 5. Validate word count
        word_count = len(markdown.split()) if markdown else 0
        if word_count < min_word_count:
            await update_resource_after_scrape(
                resource_id,
                PipelineStage.FAILED.value,
                scraped_content=None,
                failure_reason="Insufficient content",
            )
            logger.warning(
                "Scrape failed: insufficient content",
                extra={"resource_id": resource_id, "word_count": word_count},
            )
            return

        # 6. On success — build ScrapedContent and update
        scraped = ScrapedContent(
            markdown=markdown,
            title=title,
            url=url,
            extracted_at=datetime.now(UTC),
            metadata=ScrapedContentMetadata(
                word_count=word_count,
                type=resource_type,
            ),
        )
        scraped_dict = scraped.model_dump(mode="json")

        await update_resource_after_scrape(
            resource_id,
            PipelineStage.SCRAPED.value,
            scraped_content=scraped_dict,
            failure_reason=None,
        )
        logger.info(
            "Scrape completed",
            extra={
                "resource_id": resource_id,
                "pipeline_stage": PipelineStage.SCRAPED.value,
                "word_count": word_count,
            },
        )

    except Exception as e:
        failure_reason = f"{type(e).__name__}: {str(e)}"
        await update_resource_after_scrape(
            resource_id,
            PipelineStage.FAILED.value,
            scraped_content=None,
            failure_reason=failure_reason,
        )
        logger.warning(
            "Scrape failed: %s",
            failure_reason,
            extra={"resource_id": resource_id},
        )


async def _run_async(sync_fn, *args, **kwargs):
    """Run sync function in executor for CPU-bound or blocking calls."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: sync_fn(*args, **kwargs))
