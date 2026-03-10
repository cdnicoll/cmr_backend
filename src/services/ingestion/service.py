"""Ingestion service — validate scraped content and ingest into Graphiti knowledge graph."""
import json
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from src.models.config import load_settings
from src.models.resources import PipelineStage
from src.services.supabase.resources_dao import (
    atomic_transition_to_ingesting,
    get_resource_by_id,
    update_resource_after_ingestion,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_graphiti_client() -> Graphiti:
    """Build Graphiti client from env (NEO4J_*, OPENAI_API_KEY)."""
    settings = load_settings()
    if not settings.neo4j_uri or not settings.neo4j_password:
        raise ValueError("NEO4J_URI and NEO4J_PASSWORD must be set for ingestion")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY must be set for Graphiti")
    return Graphiti(
        settings.neo4j_uri,
        settings.neo4j_username or "neo4j",
        settings.neo4j_password,
    )


async def ingest_resource(resource_id: str) -> None:
    """
    Ingest a scraped resource into the knowledge graph.
    Load resource; require pipeline_stage == scraped and non-null scraped_content;
    validate word count; atomically transition to ingesting; add episode to Graphiti;
    set pipeline_stage to complete or failed with failure_reason.
    """
    settings = load_settings()
    min_word_count = settings.ingest_min_word_count

    resource = await get_resource_by_id(resource_id)
    if not resource:
        logger.warning("Resource not found", extra={"resource_id": resource_id})
        return

    current_stage = resource.get("pipeline_stage") or ""
    if current_stage != PipelineStage.SCRAPED.value:
        logger.info(
            "Skipping resource %s: not in scraped stage (current: %s)",
            resource_id,
            current_stage,
            extra={"resource_id": resource_id, "pipeline_stage": current_stage},
        )
        return

    raw_content = resource.get("scraped_content")
    if not raw_content:
        await update_resource_after_ingestion(
            resource_id,
            PipelineStage.FAILED.value,
            failure_reason="Insufficient content for ingestion",
        )
        logger.warning(
            "Ingestion failed: scraped_content is null",
            extra={"resource_id": resource_id},
        )
        return

    if isinstance(raw_content, str):
        try:
            scraped_content = json.loads(raw_content)
        except json.JSONDecodeError:
            scraped_content = {
                "markdown": raw_content,
                "metadata": {"word_count": len(raw_content.split())},
            }
    else:
        scraped_content = raw_content

    markdown = scraped_content.get("markdown") or ""
    metadata = scraped_content.get("metadata") or {}
    word_count = metadata.get("word_count")
    if word_count is None:
        word_count = len(markdown.split()) if markdown else 0

    if word_count < min_word_count:
        await update_resource_after_ingestion(
            resource_id,
            PipelineStage.FAILED.value,
            failure_reason="Insufficient content for ingestion",
        )
        logger.warning(
            "Ingestion failed: word count below threshold",
            extra={"resource_id": resource_id, "word_count": word_count},
        )
        return

    rows_updated = await atomic_transition_to_ingesting(resource_id)
    if rows_updated == 0:
        logger.info(
            "Resource already claimed or not in scraped stage",
            extra={"resource_id": resource_id},
        )
        return

    logger.info(
        "Started ingestion",
        extra={"resource_id": resource_id, "word_count": word_count},
    )

    url = resource.get("url") or scraped_content.get("url") or ""
    title = resource.get("title") or scraped_content.get("title") or ""
    source_description = title or url or "scraped resource"
    updated_at = resource.get("updated_at")
    created_at = resource.get("created_at")
    ref_ts = updated_at or created_at
    if hasattr(ref_ts, "isoformat"):
        reference_time = ref_ts
    elif ref_ts:
        reference_time = datetime.now(timezone.utc)
    else:
        reference_time = datetime.now(timezone.utc)

    try:
        graphiti = _get_graphiti_client()
        try:
            await graphiti.add_episode(
                name=f"resource_{resource_id}",
                episode_body=markdown,
                source=EpisodeType.text,
                source_description=source_description,
                reference_time=reference_time,
            )
        finally:
            await graphiti.close()

        await update_resource_after_ingestion(
            resource_id,
            PipelineStage.COMPLETE.value,
            failure_reason=None,
        )
        logger.info(
            "Ingestion completed",
            extra={"resource_id": resource_id, "pipeline_stage": PipelineStage.COMPLETE.value},
        )
    except Exception as e:
        failure_reason = f"{type(e).__name__}: {str(e)}"
        await update_resource_after_ingestion(
            resource_id,
            PipelineStage.FAILED.value,
            failure_reason=failure_reason,
        )
        logger.warning(
            "Ingestion failed: %s",
            failure_reason,
            extra={"resource_id": resource_id},
        )
