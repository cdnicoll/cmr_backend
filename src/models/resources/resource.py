"""Resource model enums."""
from enum import Enum


class ResourceType(str, Enum):
    """Resource type (website or youtube)."""

    WEBSITE = "website"
    YOUTUBE = "youtube"


class PipelineStage(str, Enum):
    """Pipeline lifecycle stage. Path: discovered → scraping → scraped → ingesting → complete (or failed)."""

    DISCOVERED = "discovered"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    INGESTING = "ingesting"
    COMPLETE = "complete"
    FAILED = "failed"
