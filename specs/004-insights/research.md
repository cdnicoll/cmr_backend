# Research: Phase 3 — Insights (AI Extraction)

**Feature**: 004-insights  
**Date**: 2025-03-01 | **Phase**: 0

## Context

Phase 3 implements AI-powered insight extraction from scraped content. The build plan and domain findings provide scope. This document consolidates decisions for traceability.

---

## 1. PydanticAI Agent Design

**Decision**: Use PydanticAI v1.0.5 with a structured output model `ResourceAnalysis`. The agent receives `scraped_content.markdown` and optional metadata (title, url, type). Output schema: `resource_overview`, `resource_insights`, `entities`, `relationships`, `temporal_context`. Each insight has category, scores (importance, originality, reliability, relevance with value/rationale/confidence), evidence, entities, relationships.

**Rationale**: PydanticAI provides type-safe LLM output and structured extraction. Domain findings specify the taxonomy; build plan requires atomic outputs for Graphiti episode constraints.

**Alternatives considered**:
- Raw prompt + JSON parse: Fragile; PydanticAI enforces schema.
- LangChain: Heavier; PydanticAI is lighter and aligns with existing stack.
- Separate extraction steps: Single agent is simpler; taxonomy is well-defined.

**Implementation notes**: Model via `MODEL_INSIGHT_EXTRACTION` env var. No `alignment` field. Produce one entity/relationship/fact per item for episode size.

**v1.x API (pin to 1.0.5)**:
```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

model = OpenAIChatModel(
    model_name=settings.model_insight_extraction,  # e.g. "x-ai/grok-4-fast"
    provider=OpenAIProvider(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key,
    ),
)
insight_agent = Agent(
    model=model,
    output_type=ResourceAnalysis,  # not result_type=
    instructions="...",            # not system_prompt= in constructor
)

result = await insight_agent.run(prompt)
analysis = result.output           # not result.data
```

---

## 2. Modal Tier and Invocation

**Decision**: Implement a standalone Modal function `extract_insights(resource_id: str)` in the **LLM tier** (same as `process_llm_job`). Use `retries=1` on the decorator. Do NOT add a job type to the jobs table. Pipeline orchestration (Phase 8) will spawn this function directly for each resource in `scraped` stage.

**Rationale**: Build plan specifies "Modal function: reads scraped content, runs agent, stores insight." LLM tier has CPU/memory for PydanticAI + OpenAI. No jobs table for insights per design.

**Alternatives considered**:
- Add `resource_insight` job type: Build plan removes jobs for pipeline stages; resource state lives on resource row.
- REST endpoint: Build plan says no manual trigger; Modal CLI suffices.

---

## 3. Atomic Selection and Race Prevention

**Decision**: Use a single Supabase update at start to set `pipeline_stage = extracting`. Condition: `WHERE id = resource_id AND pipeline_stage = 'scraped'`. Use `UPDATE ... RETURNING` to atomically claim the resource. If no rows updated, another worker claimed it or resource is not eligible; skip (log and return).

**Rationale**: Domain findings require "atomic selection + status update pattern" to prevent race when multiple workers target the same resource.

**Alternatives considered**:
- Optimistic locking with `updated_at`: Adds complexity; conditional update suffices.
- Advisory locks: Overkill; single conditional update is sufficient.

---

## 4. Content Validation

**Decision**: After fetching the resource, validate `scraped_content.metadata.word_count` (or compute from `markdown`) against `INSIGHT_MIN_WORD_COUNT` (env var, default 100). If below threshold, set `pipeline_stage = failed`, `failure_reason = "Insufficient content for insight extraction"`. Do not run the agent.

**Rationale**: Domain findings: "Content too short: Marks failed, no retry." Phase 2 uses 50 words for scrape; insight extraction benefits from more content. Default 100 is configurable.

**Alternatives considered**:
- Same threshold as scrape (50): Too low for meaningful insight extraction.
- No validation: Would waste LLM calls on near-empty content.

---

## 5. Insight Output Schema (JSONB)

**Decision**: Store agent output as JSONB with structure matching `ResourceAnalysis`:

```json
{
  "resource_overview": { "summary": "...", "tags": ["..."] },
  "resource_insights": [
    {
      "category": "market_opportunity",
      "summary": "Company A acquired a copper deposit in Chile, expanding its South American footprint.",
      "scores": {
        "importance": { "value": 0.8, "rationale": "...", "confidence": 0.9 },
        "originality": { ... },
        "reliability": { ... },
        "relevance": { ... }
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

**Rationale**: Matches domain findings taxonomy. Atomic items support Graphiti episode ingestion. No `alignment` field.

**Alternatives considered**:
- Flatter structure: Loses taxonomy; domain findings specify nested structure.
- Include alignment: Build plan omits; never implemented in legacy.

---

## 6. Failure Handling and Modal Retries

**Decision**: Wrap agent call in try/except. On exception: set `pipeline_stage = failed`, `failure_reason = f"{type(e).__name__}: {str(e)}"`. Use `retries=1` on Modal function decorator for transient LLM/API errors. No retry logic inside the agent.

**Rationale**: Build plan: "Use Modal-level retries. No retry logic inside the agent." Modal retries handle transient failures; explicit catch handles agent/validation errors.

**Alternatives considered**:
- JSON retries in agent: Build plan rejects; Modal retries suffice.
- No Modal retries: Transient rate limits would fail; one retry is reasonable.

---

## 7. Stuck Processing Reset

**Decision**: Phase 3 does not implement the recovery worker. The recovery worker is Phase 8. Phase 3 documents the expected behavior: resources stuck in `extracting` beyond `INSIGHT_STUCK_TIMEOUT_MINUTES` (configurable, default 30) should be reset to `failed` by the recovery worker. Add `INSIGHT_STUCK_TIMEOUT_MINUTES` to env/config for Phase 8 to consume. Default is 30 minutes — comfortably above the 10-min function timeout to avoid false positives.

**Rationale**: Domain findings require "stuck-processing reset with configurable timeout." Phase 8 implements recovery; Phase 3 defines the timeout and stage to watch.

**Alternatives considered**:
- Implement recovery in Phase 3: Phase 8 owns orchestration and recovery; defer.
- No timeout config: Recovery needs a value; document it now.

---

## 8. Episode Size for Graphiti

**Decision**: Phase 3 agent produces atomic, focused outputs (one entity/relationship/fact per item). No explicit truncation in Phase 3. Phase 4 adds `MAX_EPISODE_LENGTH` validation. Phase 3 prompt instructs the agent to keep each insight/entity/relationship concise to support downstream ingestion.

**Rationale**: Build plan: "Phase 3 insight extraction agent produces atomic, structured outputs which naturally keeps episodes short." Prompt engineering suffices; Phase 4 adds safety net.

**Alternatives considered**:
- Truncate in Phase 3: Phase 4 owns ingestion; keep Phase 3 focused.
- Hard limit in schema: Pydantic could enforce max length; prompt guidance is simpler.

---

## Summary

| Area | Decision | Key Rationale |
|------|----------|---------------|
| Agent | PydanticAI, ResourceAnalysis schema | Type-safe, taxonomy from domain findings |
| Modal tier | LLM tier, retries=1 | CPU/memory for agent; transient retry |
| Atomicity | UPDATE WHERE scraped RETURNING | Race prevention |
| Content validation | INSIGHT_MIN_WORD_COUNT=100 | Fail short content before agent |
| Output schema | ResourceAnalysis JSONB | Entities, relationships, scores; no alignment |
| Failure | try/except, failure_reason | Explicit marking |
| Stuck reset | Phase 8; document timeout | INSIGHT_STUCK_TIMEOUT_MINUTES |
| Episode size | Prompt for atomic output | Phase 4 adds truncation safety |
