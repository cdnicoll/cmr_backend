"""Resource-pipeline recovery: find stuck scraping/ingesting resources and mark them failed."""
from datetime import datetime, timedelta, timezone

from src.models.config import load_settings
from src.services.supabase.resources_dao import list_stuck_resources, mark_resource_failed
from src.utils.logging import get_logger

logger = get_logger(__name__)

SCRAPING_STAGE = "scraping"
INGESTING_STAGE = "ingesting"
REASON_SCRAPING = "Stuck scraping timeout"
REASON_INGESTING = "Stuck ingesting timeout"


async def run_recovery_pipeline() -> None:
    """
    Find resources stuck in scraping or ingesting (updated_at older than configurable timeouts)
    and mark them failed with a clear reason. Logs counts per stage.
    """
    settings = load_settings()
    now = datetime.now(timezone.utc)

    scrape_cutoff = now - timedelta(minutes=settings.scrape_stuck_timeout_minutes)
    ingest_cutoff = now - timedelta(minutes=settings.ingest_stuck_timeout_minutes)

    stuck_scraping = await list_stuck_resources(SCRAPING_STAGE, scrape_cutoff)
    stuck_ingesting = await list_stuck_resources(INGESTING_STAGE, ingest_cutoff)

    for rid in stuck_scraping:
        await mark_resource_failed(rid, REASON_SCRAPING)
    for rid in stuck_ingesting:
        await mark_resource_failed(rid, REASON_INGESTING)

    logger.info(
        "recovery_pipeline completed",
        extra={
            "stuck_scraping_count": len(stuck_scraping),
            "stuck_ingesting_count": len(stuck_ingesting),
            "marked_failed_scraping": len(stuck_scraping),
            "marked_failed_ingesting": len(stuck_ingesting),
        },
    )
