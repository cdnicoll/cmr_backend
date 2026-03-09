"""ResourceAnalysis Pydantic models for insight extraction agent output."""
from typing import Literal

from pydantic import BaseModel


class ScoreDimension(BaseModel):
    """Single score dimension with value, rationale, and confidence."""

    value: float
    rationale: str
    confidence: float


class InsightScores(BaseModel):
    """Scores for a single resource insight."""

    importance: ScoreDimension
    originality: ScoreDimension
    reliability: ScoreDimension
    relevance: ScoreDimension


class ResourceInsight(BaseModel):
    """A single insight extracted from a resource."""

    category: Literal[
        "market_opportunity",
        "risk_factor",
        "trend_identification",
        "competitive_intelligence",
        "regulatory_impact",
        "technical_analysis",
        "fundamental_shift",
        "sentiment_indicator",
    ]
    summary: str
    scores: InsightScores
    evidence: str
    entities: list[str]
    relationships: list[str]


class Entity(BaseModel):
    """An entity extracted from the resource."""

    type: Literal[
        "commodity",
        "company",
        "institution",
        "person",
        "location",
        "concept",
        "event",
    ]
    name: str
    context: str


class Relationship(BaseModel):
    """A relationship between entities."""

    type: Literal[
        "influences",
        "influenced_by",
        "competes_with",
        "partners_with",
        "owns",
        "located_in",
        "mentioned_in",
        "related_to",
    ]
    source: str
    target: str
    context: str


class ResourceOverview(BaseModel):
    """High-level overview of the resource."""

    summary: str
    tags: list[str]


class TemporalContext(BaseModel):
    """Temporal context for the resource content."""

    timeframe: str
    events: list[str]


class ResourceAnalysis(BaseModel):
    """Full analysis output from the insight extraction agent."""

    resource_overview: ResourceOverview
    resource_insights: list[ResourceInsight]
    entities: list[Entity]
    relationships: list[Relationship]
    temporal_context: TemporalContext | None = None
