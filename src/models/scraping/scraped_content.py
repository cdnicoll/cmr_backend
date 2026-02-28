"""Scraped content schema for JSONB storage."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScrapedContentMetadata(BaseModel):
    """Metadata for scraped content."""

    word_count: int
    type: Literal["website", "youtube"]


class ScrapedContent(BaseModel):
    """Scraped content stored in resources.scraped_content JSONB."""

    markdown: str
    title: str
    url: str
    extracted_at: datetime
    metadata: ScrapedContentMetadata
