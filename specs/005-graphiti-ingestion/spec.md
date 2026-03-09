# Feature Specification: Knowledge Graph Ingestion from Scraped Content

**Feature Branch**: `005-graphiti-ingestion`  
**Created**: 2025-03-09  
**Status**: Draft  
**Input**: Phase 4: Knowledge Graph — Graphiti Ingestion from scraped content only. Ingestion worker (Modal, resource_id, validate, Graphiti add episode, pipeline_stage complete/failed). Remove Phase 3 extraction code. Graphiti as single extractor; Neo4j env in Modal; episode format; failure handling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest Scraped Content into the Knowledge Graph (Priority: P1)

An operator triggers ingestion for a resource that has already been scraped. The system validates that the resource has sufficient scraped content, marks the resource as "ingesting," sends the scraped text to the external knowledge-graph service (which performs entity and relationship extraction and merges into the graph), and then marks the resource as complete or failed. The pipeline moves only from scraped → ingesting → complete (or failed); there is no separate extraction step.

**Why this priority**: Delivers the core value of the phase — getting scraped content into the knowledge graph so it can be queried for trends and intelligence.

**Independent Test**: Trigger the ingestion worker for a resource in "scraped" stage with valid scraped content; confirm the resource transitions to "complete" and that the graph contains new or updated entities/relationships from that content.

**Acceptance Scenarios**:

1. **Given** a resource in scraped stage with valid scraped content (e.g. markdown, URL, title), **When** the ingestion worker is run for that resource, **Then** the resource transitions to ingesting, then to complete, and the knowledge graph reflects the ingested content (entities, relationships, provenance).
2. **Given** a resource in scraped stage, **When** the worker runs successfully, **Then** the system records completion (e.g. pipeline stage = complete) and does not leave the resource stuck in ingesting.
3. **Given** a resource in scraped stage with scraped content that meets a defined minimum size, **When** the ingestion worker runs, **Then** the content is sent to the knowledge-graph service in the expected episode format (text plus optional provenance metadata).

---

### User Story 2 - Validate Content and Record Failures (Priority: P2)

The system rejects or fails resources whose scraped content is missing or below a minimum threshold (e.g. word count). When ingestion fails for any reason (validation, graph service error, timeout), the system marks the resource as failed and records a reason so operators can diagnose and decide whether to retry.

**Why this priority**: Prevents invalid or empty content from being sent to the graph and ensures failed resources are actionable.

**Independent Test**: Run the ingestion worker for a resource with very short or missing content; confirm the resource is marked failed with a clear reason and is not left in ingesting.

**Acceptance Scenarios**:

1. **Given** a resource in scraped stage with missing or very short scraped content, **When** the ingestion worker runs, **Then** the resource is not sent to the graph and is marked failed with a recorded failure reason.
2. **Given** a resource in scraped stage, **When** the knowledge-graph service or connectivity fails during ingestion, **Then** the resource is marked failed and the failure reason is stored for operator review.
3. **Given** a failed resource, **When** an operator inspects it, **Then** they can see why it failed (e.g. validation, timeout, service error) without needing to inspect logs only.

---

### User Story 3 - Single Pipeline Path and Removal of Old Extraction (Priority: P3)

The content pipeline has a single path from scraped to ingesting to complete (or failed). The previous extraction step (separate AI extraction that wrote structured insight data before graph ingestion) is removed: no separate "extracting" or "extracted" stages, no insight-extraction worker, and no dependency on that extraction for ingestion. Operators and runbook use only the new ingestion flow.

**Why this priority**: Simplifies the pipeline and avoids confusion between two extraction paths; ensures one source of truth for graph content.

**Independent Test**: After implementation, confirm there is no way to run the old extraction worker, no code paths that transition resources to extracting/extracted, and runbook/docs describe only scraped → ingesting → complete.

**Acceptance Scenarios**:

1. **Given** the new ingestion worker is in place, **When** a resource reaches scraped stage, **Then** the only path to complete is via the new ingestion worker (scraped → ingesting → complete); no extracting or extracted stages exist.
2. **Given** the codebase and runbook, **When** an operator follows documentation, **Then** they see only the ingestion-from-scraped flow; references to the old insight-extraction trigger, worker, and pipeline stages are removed or deprecated.
3. **Given** a resource record, **When** ingestion is the only extraction path, **Then** any legacy "insight" field is either deprecated, ignored, or removed so it does not affect ingestion behavior.

---

### Edge Cases

- What happens when scraped content exists but is below the minimum word count? System MUST mark the resource as failed with a validation-related failure reason and MUST NOT send content to the graph.
- What happens when the knowledge-graph service is temporarily unavailable? System MUST mark the resource as failed and record the failure reason (e.g. connection or timeout); recovery/retry is out of scope for this phase.
- What happens when a resource is already in "ingesting" (e.g. a previous run left it stuck)? This phase does not implement automatic reset; a later phase (e.g. recovery worker) will handle stuck ingesting; the spec only requires that a configurable timeout for "stuck ingesting" is documented or configurable so that phase can use it.
- What happens when the same resource is triggered for ingestion twice concurrently? System SHOULD avoid double-processing (e.g. by transitioning to ingesting atomically so only one worker proceeds); failure reason MUST still be set if the second run finds the resource already ingesting or complete.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an ingestion worker that accepts a resource identifier, loads the resource and its scraped content (e.g. markdown, URL, title), and sends that content to the external knowledge-graph service for entity/relationship extraction and merge.
- **FR-002**: System MUST validate scraped content before ingestion (e.g. presence and minimum word count) and MUST NOT call the graph service when validation fails.
- **FR-003**: System MUST transition the resource to an "ingesting" state before calling the graph service and MUST set the resource to "complete" on success or "failed" on failure, with no separate "extracting" or "extracted" pipeline stages.
- **FR-004**: System MUST record a failure reason when a resource is set to failed (validation, graph service error, timeout, or other) so operators can diagnose and decide retry.
- **FR-005**: System MUST configure and use credentials and connection settings for the graph database and the graph service (e.g. Neo4j and Graphiti) in a secure, environment-specific way (e.g. secrets) for the worker.
- **FR-006**: System MUST pass scraped text and optional provenance metadata (e.g. source URL, title) to the graph service in the episode format required by that service.
- **FR-007**: System MUST remove the previous extraction path: the PydanticAI insight agent, the extract_insights service method, the extract_insights worker, DAO methods used only for that extraction, and insight-related models/config; and MUST update the runbook to describe only the scraped → ingesting → complete flow.
- **FR-008**: System MUST support a configurable minimum content size (e.g. minimum word count) for eligibility for ingestion; value MUST be configurable per environment.
- **FR-009**: System MUST document or support a configurable timeout for "stuck ingesting" so a future recovery phase can reset resources that have been in ingesting beyond that timeout.

### Key Entities

- **Resource**: The content item (URL, type, pipeline stage, failure reason). Holds scraped content (e.g. markdown, URL, title) and moves through stages: scraped → ingesting → complete or failed.
- **Scraped content**: The output of scraping (e.g. markdown body, source URL, title). Input to ingestion; must meet minimum size and presence rules.
- **Pipeline stage**: The resource’s state in the pipeline. For this phase: scraped, ingesting, complete, failed (no extracting or extracted).
- **Knowledge graph (external)**: Entities, relationships, and episodic mentions produced by the graph service from ingested text; merge and temporal behavior are owned by the graph service.

## Assumptions

- The external knowledge-graph service (Graphiti) performs LLM-based entity/relationship extraction, entity merge, and temporal edges; the worker only sends episode(s) (text + optional metadata) and does not implement extraction logic.
- Neo4j (and any Graphiti-specific) connection details are provided via environment or secrets; the worker runs in a hosted environment (e.g. Modal) where those secrets are available.
- A reasonable default for minimum content size (e.g. 100 words) is used unless otherwise configured; the exact default is an implementation choice.
- Stuck "ingesting" recovery (resetting resources that have been ingesting too long) is implemented in a later phase (e.g. Phase 8); this phase only ensures the concept is documented or configurable.
- The "insight" column or legacy insight-related storage on resources may be deprecated or left unpopulated; ingestion does not depend on it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can trigger ingestion for a scraped resource and see it move to complete within a defined timeout (e.g. within minutes under normal conditions), with the knowledge graph updated.
- **SC-002**: Resources with missing or below-threshold scraped content are never sent to the graph and are always marked failed with a recorded reason.
- **SC-003**: 100% of failed ingestion attempts have a stored failure reason so operators can distinguish validation, connectivity, and service errors without inspecting logs only.
- **SC-004**: The pipeline has a single path from scraped to complete (via ingesting); no code or runbook references the old extraction worker or extracting/extracted stages as active paths.
- **SC-005**: Runbook and documentation allow an operator to run and verify the ingestion flow (trigger worker, check pipeline stage, verify graph) without reference to removed extraction steps.

## References for implementation planning

When creating the Phase 4 plan and tasks, use **`_local/build-plan.md`** — Phase 4 section and **Phase 4 pre-plan (before spec planning)** — for:

- Graphiti API: `add_episode()` signature, episode parameters (name, episode_body, source=text, source_description, reference_time), and [Adding Episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes).
- Runtime dependencies: `graphiti-core`, Neo4j, LLM/embedder; env vars (e.g. `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `OPENAI_API_KEY`) and Modal secrets.
- Config names: minimum content (e.g. `INGEST_MIN_WORD_COUNT`, default 100), stuck-ingesting timeout (e.g. `INGEST_STUCK_TIMEOUT_MINUTES`, default 30).
- Runbook: replace "Insight extraction (Phase 3)" with "Ingest to Graphiti", worker command (e.g. `modal run ...::ingest_resource --resource-id <uuid>`).
