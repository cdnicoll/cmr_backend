# Data Model: Phase 3 — Insights (AI Extraction)

**Feature**: 004-insights  
**Date**: 2025-03-01 | **Phase**: 1

## Entities

### 1. Resource (extended)

No new table. The `resources` table (from Phase 1) is extended in usage:

| Field | Phase 3 Usage |
|-------|---------------|
| id | Input to extract_insights function |
| scraped_content | Read; extract markdown, title, metadata |
| pipeline_stage | Transitions: `scraped` → `extracting` → `extracted` or `failed` |
| failure_reason | Populated on failure |
| insight | Populated on success (JSONB) |
| updated_at | Updated on each stage change |

**State transitions** (Phase 3):

- `scraped` → `extracting` (at extraction start; conditional on current stage)
- `extracting` → `extracted` (on success)
- `extracting` → `failed` (on error, content too short, or LLM exception)
- Skip if not `scraped` (e.g. already `extracted` or `complete`)

---

### 2. Insight (JSONB schema)

Stored in `resources.insight`. Not a separate table.

```json
{
  "resource_overview": {
    "summary": "Brief summary of the resource content",
    "tags": ["mining", "copper", "market"]
  },
  "resource_insights": [
    {
      "category": "market_opportunity",
      "summary": "Company A acquired a copper deposit in Chile, expanding its South American footprint.",
      "scores": {
        "importance": { "value": 0.8, "rationale": "...", "confidence": 0.9 },
        "originality": { "value": 0.6, "rationale": "...", "confidence": 0.85 },
        "reliability": { "value": 0.9, "rationale": "...", "confidence": 0.95 },
        "relevance": { "value": 0.7, "rationale": "...", "confidence": 0.8 }
      },
      "evidence": "Quote or excerpt supporting the insight",
      "entities": ["Company A", "Commodity X"],
      "relationships": ["Company A influences Commodity X"]
    }
  ],
  "entities": [
    { "type": "company", "name": "Company A", "context": "..." },
    { "type": "commodity", "name": "Copper", "context": "..." }
  ],
  "relationships": [
    { "type": "influences", "source": "Company A", "target": "Copper", "context": "..." }
  ],
  "temporal_context": {
    "timeframe": "Q1 2025",
    "events": ["Event 1", "Event 2"]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| resource_overview | object | summary, tags |
| resource_insights | array | Insights with category, scores, evidence, entities, relationships |
| entities | array | Entity objects: type, name, context |
| relationships | array | Relationship objects: type, source, target, context |
| temporal_context | object | timeframe, events |

**Insight categories**: market_opportunity, risk_factor, trend_identification, competitive_intelligence, regulatory_impact, technical_analysis, fundamental_shift, sentiment_indicator

**Entity types**: commodity, company, institution, person, location, concept, event

**Relationship types**: influences, influenced_by, competes_with, partners_with, owns, located_in, mentioned_in, related_to

**Scores**: importance, originality, reliability, relevance — each with value (0–1), rationale, confidence

**Validation**: Pydantic model `ResourceAnalysis` for serialization/validation before DB write. No `alignment` field.

---

## Validation Rules

### Resource (extraction eligibility)

- `pipeline_stage` MUST be `scraped` for extraction to start
- `scraped_content` MUST be non-null and contain `markdown`
- `scraped_content.metadata.word_count` (or computed) MUST be >= `INSIGHT_MIN_WORD_COUNT` (default 100, env `INSIGHT_MIN_WORD_COUNT`)

### Insight (agent output)

- `resource_overview` MUST be present
- `resource_insights` MUST be an array (may be empty)
- `entities` and `relationships` MUST be arrays (may be empty)
- Each insight MUST have `category` from the defined set
- Each score MUST have `value`, `rationale`, `confidence`
- MUST NOT include `alignment` field

---

## Migration

**No new migration in Phase 3.** The `insight` JSONB column exists from Phase 1. Phase 3 only writes to it.

---

## API Schemas (Pydantic)

### ResourceAnalysis (agent output)

```python
from typing import Literal
from pydantic import BaseModel


class ScoreDimension(BaseModel):
    value: float
    rationale: str
    confidence: float


class InsightScores(BaseModel):
    importance: ScoreDimension
    originality: ScoreDimension
    reliability: ScoreDimension
    relevance: ScoreDimension


class ResourceInsight(BaseModel):
    category: Literal[
        "market_opportunity", "risk_factor", "trend_identification",
        "competitive_intelligence", "regulatory_impact", "technical_analysis",
        "fundamental_shift", "sentiment_indicator"
    ]
    summary: str
    scores: InsightScores
    evidence: str
    entities: list[str]
    relationships: list[str]


class Entity(BaseModel):
    type: Literal["commodity", "company", "institution", "person", "location", "concept", "event"]
    name: str
    context: str


class Relationship(BaseModel):
    type: Literal["influences", "influenced_by", "competes_with", "partners_with", "owns", "located_in", "mentioned_in", "related_to"]
    source: str
    target: str
    context: str


class ResourceOverview(BaseModel):
    summary: str
    tags: list[str]


class TemporalContext(BaseModel):
    timeframe: str
    events: list[str]


class ResourceAnalysis(BaseModel):
    resource_overview: ResourceOverview
    resource_insights: list[ResourceInsight]
    entities: list[Entity]
    relationships: list[Relationship]
    temporal_context: TemporalContext | None = None
```

### Extract Insights Function Signature

```python
@app.function(
    image=image,      # standard image — no browser needed
    timeout=600,      # 10 min — generous for LLM API round-trips on long content
    cpu=1,            # I/O-bound; LLM call is the bottleneck, not CPU
    memory=1024,      # PydanticAI + OpenAI client; modest footprint
    retries=1,
    secrets=_secrets,
)
async def extract_insights(resource_id: str) -> None:
    """Extract insights from a scraped resource. Updates pipeline_stage and insight."""
```

Modal retries: `retries=1` — one retry for transient LLM/API failures.
