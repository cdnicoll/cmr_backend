"""Resource model enums."""
from enum import Enum


class ResourceType(str, Enum):
    """Resource type (website or youtube)."""

    WEBSITE = "website"
    YOUTUBE = "youtube"


class PipelineStage(str, Enum):
    """Pipeline lifecycle stage."""

    DISCOVERED = "discovered"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    INGESTING = "ingesting"
    COMPLETE = "complete"
    FAILED = "failed"
