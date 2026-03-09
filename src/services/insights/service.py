"""Insights service — orchestrates extraction from scraped content."""
import json

from src.models.config import load_settings
from src.models.resources import PipelineStage
from src.services.insights.agent import get_insight_agent
from src.services.supabase.resources_dao import (
    atomic_transition_to_extracting,
    get_resource_by_id,
    update_resource_after_extraction,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class InsightsService:
    """Service for AI-powered insight extraction from scraped content."""

    @staticmethod
    async def extract_insights(resource_id: str) -> None:
        """
        Extract insights from a scraped resource by ID.
        Fetches resource, validates content, runs agent, updates DB.
        """
        settings = load_settings()
        min_word_count = settings.insight_min_word_count

        # 1. Fetch resource
        resource = await get_resource_by_id(resource_id)
        if not resource:
            logger.warning("Resource not found", extra={"resource_id": resource_id})
            return

        current_stage = resource.get("pipeline_stage") or ""

        # 2. Eligibility check — skip if not scraped
        if current_stage != PipelineStage.SCRAPED.value:
            logger.info(
                "Skipping resource %s: not in scraped stage (current: %s)",
                resource_id,
                current_stage,
                extra={"resource_id": resource_id, "pipeline_stage": current_stage},
            )
            return

        # 3. Content validation — scraped_content must be non-null
        raw_content = resource.get("scraped_content")
        if not raw_content:
            await update_resource_after_extraction(
                resource_id,
                PipelineStage.FAILED.value,
                insight=None,
                failure_reason="Insufficient content for insight extraction",
            )
            logger.warning(
                "Extraction failed: scraped_content is null",
                extra={"resource_id": resource_id},
            )
            return

        # Normalize: DB may return JSONB as dict or as JSON string
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

        # 4. Word count validation
        markdown = scraped_content.get("markdown") or ""
        metadata = scraped_content.get("metadata") or {}
        word_count = metadata.get("word_count")
        if word_count is None:
            word_count = len(markdown.split()) if markdown else 0

        if word_count < min_word_count:
            await update_resource_after_extraction(
                resource_id,
                PipelineStage.FAILED.value,
                insight=None,
                failure_reason="Insufficient content for insight extraction",
            )
            logger.warning(
                "Extraction failed: word count below threshold",
                extra={"resource_id": resource_id, "word_count": word_count},
            )
            return

        # 5. Atomic transition to extracting
        rows_updated = await atomic_transition_to_extracting(resource_id)
        if rows_updated == 0:
            logger.info(
                "Resource already claimed by another worker",
                extra={"resource_id": resource_id},
            )
            return

        logger.info(
            "Started insight extraction",
            extra={"resource_id": resource_id, "word_count": word_count},
        )

        try:
            # 6. Build prompt from scraped content
            title = scraped_content.get("title") or ""
            url = scraped_content.get("url") or ""
            resource_type = metadata.get("type") or "website"

            prompt_parts = [f"# {title}\n\n" if title else "", markdown]
            if url:
                prompt_parts.append(f"\n\nSource: {url} ({resource_type})")
            prompt = "".join(prompt_parts).strip() or markdown

            # 7. Run agent
            result = await get_insight_agent().run(prompt)
            analysis = result.output

            # 8. On success — write insight (exclude alignment; model doesn't have it)
            insight_dict = analysis.model_dump(mode="json")
            await update_resource_after_extraction(
                resource_id,
                PipelineStage.EXTRACTED.value,
                insight=insight_dict,
                failure_reason=None,
            )
            logger.info(
                "Extraction completed",
                extra={
                    "resource_id": resource_id,
                    "pipeline_stage": PipelineStage.EXTRACTED.value,
                    "insight_count": len(analysis.resource_insights),
                },
            )

        except Exception as e:
            failure_reason = f"{type(e).__name__}: {str(e)}"
            await update_resource_after_extraction(
                resource_id,
                PipelineStage.FAILED.value,
                insight=None,
                failure_reason=failure_reason,
            )
            logger.warning(
                "Extraction failed: %s",
                failure_reason,
                extra={"resource_id": resource_id},
            )
