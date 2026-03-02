# Feature Specification: Phase 3 — Insights (AI Extraction)

**Feature Branch**: `004-insights`  
**Created**: 2025-03-01  
**Status**: Draft  
**Input**: `_local/build-plan.md` Phase 3, `_local/domain_findings/domains/03-insights.md`, `_local/starter-kit/patterns.md`, `_local/starter-kit/modal-jobs.md`

## Summary

Phase 3 implements **AI-powered insight extraction** from scraped content. A Modal function accepts `resource_id`, reads `scraped_content` from the resource, runs a PydanticAI agent to extract entities, relationships, and scored insights, and stores the result in the `insight` JSONB column. The resource transitions `pipeline_stage` from `scraped` → `extracting` → `extracted` (or `failed`). The output structure supports downstream Graphiti ingestion (Phase 4) with atomic, focused episodes.

## Clarifications (from build-plan.md)

- **Alignment score**: Omit entirely. Never implemented in legacy; not needed in rebuild.
- **Retry strategy**: Use Modal-level retries only. No retry logic inside the agent.
- **Model config**: Use `MODEL_INSIGHT_EXTRACTION` env var. Each task gets its own env var; no global default.

## User Scenarios & Testing

### User Story 1 — Extract Insights from Scraped Resource (Priority: P1)

As the system (or a developer via Modal CLI), I need to run the insight extraction worker with a `resource_id` so entities, relationships, and scored insights are extracted and stored for downstream graph ingestion.

**Independent Test**: Spawn insight worker with a resource in `scraped` stage; confirm `pipeline_stage` → `extracted` and `insight` populated.

**Acceptance Scenarios**:

1. **Given** a resource with `pipeline_stage = scraped` and valid `scraped_content`, **When** the insight worker runs, **Then** the resource transitions `scraped` → `extracting` → `extracted` and `insight` JSONB is populated
2. **Given** a resource with very short scraped content (below `INSIGHT_MIN_WORD_COUNT`), **When** the insight worker runs, **Then** `pipeline_stage = failed` and `failure_reason` is populated
3. **Given** a resource already in `extracted` or `complete`, **When** the insight worker runs, **Then** it skips or fails gracefully (no overwrite)
4. **Given** the insight agent returns structured output, **When** the worker completes, **Then** `insight` contains entities, relationships, resource_insights with categories and scores (importance, originality, reliability, relevance)
5. **Given** the insight agent raises an exception (LLM error, rate limit), **When** the worker handles it, **Then** `pipeline_stage = failed` and `failure_reason` is populated

---

### User Story 2 — Pipeline Stage Transitions (Priority: P1)

As the system, `pipeline_stage` must reflect extraction progress so downstream workers and recovery logic can reason about resource state.

**Independent Test**: Inspect resource row before/after extraction; confirm stage transitions and `updated_at` changes.

**Acceptance Scenarios**:

1. **Given** extraction starts, **Then** `pipeline_stage` is set to `extracting` atomically (conditional on `scraped`)
2. **Given** extraction succeeds, **Then** `pipeline_stage` is set to `extracted`
3. **Given** extraction fails (content too short, LLM error), **Then** `pipeline_stage` is set to `failed` and `failure_reason` contains error type and message

---

### User Story 3 — Atomic Selection and Stuck Processing (Priority: P2)

As the system, the insight worker must prevent race conditions when multiple workers run, and stuck resources must be recoverable.

**Independent Test**: Spawn multiple workers for the same resource; confirm only one succeeds. Simulate stuck resource; confirm recovery resets it.

**Acceptance Scenarios**:

1. **Given** two workers attempt to process the same resource, **Then** only one succeeds (atomic `UPDATE ... WHERE pipeline_stage = scraped`); the other skips
2. **Given** a resource stuck in `extracting` beyond `INSIGHT_STUCK_TIMEOUT_MINUTES`, **When** the recovery worker runs (Phase 8), **Then** it resets to `failed` with a timeout reason

---

## Edge Cases (from domain findings)

- **Race condition prevention**: `UPDATE ... RETURNING` atomically selects and marks `extracting`. Only transition from `scraped` to `extracting`; if already claimed, skip.
- **Stuck processing**: `reset_processing_resources(max_age_minutes)` resets `extracting` → eligible for retry (or `failed` per Phase 8 design). Configurable via `INSIGHT_STUCK_TIMEOUT_MINUTES`.
- **Content too short**: If `word_count < INSIGHT_MIN_WORD_COUNT` (default 100, may differ from scrape threshold), mark `failed` with `failure_reason = "Insufficient content for insight extraction"`. No retry.
- **JSON parsing**: Modal retries handle transient LLM/API errors. No JSON retry logic inside the agent.
- **Alignment score**: Explicitly NOT generated. Omit from output schema.

## Requirements

### Functional Requirements

- **FR-001**: Modal insight extraction function MUST accept `resource_id` (UUID) and fetch the resource from Supabase
- **FR-002**: Extraction function MUST transition `pipeline_stage`: `scraped` → `extracting` at start (atomically), then `extracted` or `failed` on completion
- **FR-003**: Extraction function MUST read `scraped_content` from the resource; extract metadata (title, markdown, type)
- **FR-004**: Extraction function MUST validate content length; if `word_count < INSIGHT_MIN_WORD_COUNT` (default 100), mark `failed` with `failure_reason`
- **FR-005**: Extraction function MUST run the PydanticAI insight agent with `scraped_content.markdown` as input
- **FR-006**: Agent output MUST conform to `ResourceAnalysis` schema: `resource_overview`, `resource_insights`, `entities`, `relationships`, `temporal_context`
- **FR-007**: Extraction function MUST store agent output in `insight` JSONB on the resource row
- **FR-008**: Extraction function MUST populate `failure_reason` when `pipeline_stage = failed`
- **FR-009**: Extraction function MUST skip or fail gracefully when resource is not in `scraped` (e.g. already `extracted`)
- **FR-010**: Modal function decorator MUST use `retries=1` (one retry for transient failures)
- **FR-011**: Agent output MUST NOT include `alignment` field
- **FR-012**: Agent MUST produce atomic, focused insights (one entity/relationship/fact per item) to support Graphiti episode size constraints (<400 chars)

### Key Entities

- **Resource** (existing): `id`, `url`, `type`, `pipeline_stage`, `failure_reason`, `scraped_content`, `insight`, `updated_at`
- **Insight schema** (JSONB): `ResourceAnalysis` — `resource_overview`, `resource_insights`, `entities`, `relationships`, `temporal_context`
- **Insight categories**: market_opportunity, risk_factor, trend_identification, competitive_intelligence, regulatory_impact, technical_analysis, fundamental_shift, sentiment_indicator
- **Entity types**: commodity, company, institution, person, location, concept, event
- **Relationship types**: influences, influenced_by, competes_with, partners_with, owns, located_in, mentioned_in, related_to
- **Scores**: importance, originality, reliability, relevance (each: value, rationale, confidence)

## Success Criteria

- **SC-001**: Spawn insight worker with `resource_id`; resource transitions to `extracted` with `insight` populated
- **SC-002**: `insight` structure contains entities, relationships, resource_insights with categories and scores
- **SC-003**: No `alignment` field in insight output
- **SC-004**: Very short content results in `pipeline_stage = failed`, `failure_reason` populated
- **SC-005**: No resources left stuck in `extracting` after worker completes (success or failure)
- **SC-006**: Atomic selection prevents double-processing when multiple workers target the same resource
