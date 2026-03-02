# Insight Extraction Worker Contract

**Type**: Modal function (internal)  
**Invocation**: `modal run` or `extract_insights.spawn(resource_id)`  
**Auth**: Modal secrets (Supabase service role for DB access, LLM credentials for agent)

---

## extract_insights(resource_id: str)

Extracts insights from a scraped resource by ID. Fetches the resource from Supabase, validates content length, runs the PydanticAI insight agent, and updates the resource row.

**Modal decorator**:
```python
@app.function(
    image=image,      # standard image — no browser needed
    timeout=600,      # 10 min — generous for LLM API round-trips on long content
    cpu=1,            # I/O-bound; LLM call is the bottleneck, not CPU
    memory=1024,      # PydanticAI + OpenAI client; modest footprint
    retries=1,
    secrets=_secrets,
)
```
One retry for transient LLM/API failures. No retry logic inside the function.

### Parameters

| Name | Type | Required | Description |
|-----|------|----------|-------------|
| resource_id | str (UUID) | Yes | Primary key of the resource to extract insights from |

### Behavior

1. **Fetch resource**: Query `resources` by `id`. If not found, log and return.
2. **Eligibility check**: If `pipeline_stage != scraped`, skip (log and return). No overwrite of completed insights.
3. **Content validation**: If `scraped_content` is null or `word_count < INSIGHT_MIN_WORD_COUNT` (default 100), set `pipeline_stage = failed`, `failure_reason = "Insufficient content for insight extraction"`, return.
4. **Transition to extracting**: Atomic update `pipeline_stage = extracting` where `id = resource_id` and `pipeline_stage = scraped`. If no rows updated, another worker may have claimed it; return.
5. **Run agent**: Pass `scraped_content.markdown` (and optional title, url, type) to PydanticAI insight agent. Agent returns `ResourceAnalysis`.
6. **On success**: Update `pipeline_stage = extracted`, `insight = <ResourceAnalysis JSON>`
7. **On failure**: Update `pipeline_stage = failed`, `failure_reason = "{ErrorType}: {message}"`

### ResourceAnalysis JSONB Structure

```json
{
  "resource_overview": { "summary": "...", "tags": ["..."] },
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
      "evidence": "...",
      "entities": ["..."],
      "relationships": ["..."]
    }
  ],
  "entities": [ { "type": "company", "name": "...", "context": "..." } ],
  "relationships": [ { "type": "influences", "source": "...", "target": "...", "context": "..." } ],
  "temporal_context": { "timeframe": "...", "events": ["..."] }
}
```

**Note**: No `alignment` field. Agent produces atomic items for Graphiti episode ingestion.

### Errors

- **Resource not found**: Log; return (no exception)
- **Insufficient content** (word_count < INSIGHT_MIN_WORD_COUNT): Mark `failed` with `failure_reason = "Insufficient content for insight extraction"`
- **Not eligible** (stage != scraped): Log; return
- **LLM/Agent exception**: Catch; mark `failed` with `failure_reason`
- **Modal timeout** (5 min): Process killed; resource may remain `extracting` until recovery (Phase 8)

### Return

`None` (void). Side effects: DB updates only.

---

## Invocation Examples

### Modal CLI

```bash
modal run src.deployment.modal_workers::extract_insights --resource-id "<uuid>"
```

### From Python (e.g. pipeline orchestration in Phase 8)

```python
from src.deployment.modal_workers import extract_insights
extract_insights.spawn("<resource-uuid>")
```

---

## Configuration

- `MODEL_INSIGHT_EXTRACTION` (required): LLM model for insight extraction (e.g. `gpt-4o`)
- `INSIGHT_MIN_WORD_COUNT` (optional, default 100): Minimum word count for extraction; below this, mark `failed`
- `INSIGHT_STUCK_TIMEOUT_MINUTES` (optional, default 30): Used by recovery worker (Phase 8) to reset stuck `extracting` resources; set above the 10-min function timeout to avoid false positives

## Dependencies

- Supabase client (service role) — from Modal secrets
- PydanticAI — for structured agent
- OpenAI (or configured provider) — for LLM
- LLM tier image — CPU/memory for agent
