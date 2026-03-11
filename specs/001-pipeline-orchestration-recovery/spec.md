# Feature Specification: Pipeline Orchestration and Recovery

**Feature Branch**: `001-pipeline-orchestration-recovery`  
**Created**: 2025-03-10  
**Status**: Draft  
**Input**: User description: "Phase 8: Pipeline Orchestration and Recovery only. Orchestration is discovery → scrape → ingest (spawn chain). Recovery is for resources (stuck scraping/ingesting), not the jobs table. Add resource-pipeline recovery pattern (e.g. scheduled function to mark stuck resources failed); do not reintroduce recover_orphaned_jobs."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - End-to-End Pipeline Run (Priority: P1)

As an operator, I want the system to run the full content pipeline on a schedule so that new content from configured discovery sources is discovered, scraped, and ingested into the knowledge graph without manual steps.

**Why this priority**: The primary value of Phase 8 is a single, reliable pipeline from discovery to graph. Without this, the system cannot operate autonomously.

**Independent Test**: Trigger the scheduled discovery run; confirm new resources are created, then flow through scraping and ingestion until they reach a terminal stage (complete or failed). Verify records in the knowledge graph for completed resources.

**Acceptance Scenarios**:

1. **Given** at least one configured discovery source, **When** the scheduled discovery run executes, **Then** new URLs are created as resources in the initial pipeline stage and the system automatically starts scraping for each new resource.
2. **Given** resources that have just been scraped successfully, **When** the pipeline runs, **Then** those resources are automatically sent to ingestion and progress to a terminal stage (complete or failed).
3. **Given** the pipeline has run, **When** an operator inspects the system, **Then** they can see resources progressing through the defined pipeline stages in order (discovered → scraping → scraped → ingesting → complete or failed).

---

### User Story 2 - Resource-Pipeline Recovery for Stuck Resources (Priority: P2)

As an operator, I want resources that have been stuck in a non-terminal stage (e.g. scraping or ingesting) for too long to be marked as failed automatically so that they do not block reporting and can be investigated or retried manually.

**Why this priority**: Stuck resources (e.g. due to timeouts or worker crashes) must be cleared so the pipeline state stays accurate and operators can act on failures.

**Independent Test**: Manually set a resource to a mid-pipeline stage with an old last-updated time; run the recovery process; confirm the resource is marked failed with a reason indicating timeout/stuck.

**Acceptance Scenarios**:

1. **Given** a resource in a mid-pipeline stage (e.g. scraping or ingesting) whose last update is older than the configured stuck threshold, **When** the scheduled recovery runs, **Then** that resource is marked as failed and a reason is recorded (e.g. stuck or timeout).
2. **Given** resources that are actively being processed (recently updated), **When** the recovery runs, **Then** those resources are not changed.
3. **Given** a resource already in a terminal stage (complete or failed), **When** the recovery runs, **Then** that resource is left unchanged.

---

### User Story 3 - Manual Re-queue of Failed Resources (Priority: P3)

As an operator, I want to re-queue a failed resource so that it re-enters the pipeline from an early stage (e.g. discovered) and is retried, without automatic retries that could overload or re-hit blocking sources.

**Why this priority**: Operators need a way to retry after investigating failure reasons; automatic retries are explicitly out of scope to avoid hammering blocked sources.

**Independent Test**: Mark a resource as failed, then perform the manual re-queue action; confirm the resource returns to an early stage and is picked up again by the pipeline.

**Acceptance Scenarios**:

1. **Given** a resource in a failed state with a recorded failure reason, **When** an operator performs the manual re-queue action for that resource, **Then** the resource is reset to an early pipeline stage (e.g. discovered) so it will be processed again.
2. **Given** a resource in a non-failed stage, **When** an operator attempts re-queue, **Then** the system either allows it (e.g. for discovered/scraped) or clearly indicates that re-queue applies to failed resources.

---

### User Story 4 - Manual Triggers for Pipeline Stages (Priority: P3)

As an operator or developer, I want to trigger discovery, scraping, or ingestion manually for a subset of resources (or for discovery, a dry run) so that I can debug, backfill, or test without waiting for the schedule.

**Why this priority**: Manual triggers support operations and development; they are not required for the main scheduled flow.

**Independent Test**: Invoke the manual trigger for each stage (discovery with dry-run, scrape for specific resources, ingest for specific resources); confirm the expected stage runs and state changes occur.

**Acceptance Scenarios**:

1. **Given** discovery is configured, **When** an operator runs discovery in dry-run mode, **Then** the system reports what it would create or process without creating or updating resources.
2. **Given** resources eligible for scraping (e.g. in discovered stage), **When** an operator triggers scraping for those resources, **Then** scraping runs for them and their pipeline stage advances.
3. **Given** resources eligible for ingestion (e.g. in scraped stage), **When** an operator triggers ingestion for those resources, **Then** ingestion runs and their pipeline stage advances to complete or failed.

---

### Edge Cases

- What happens when discovery finds no new URLs? The pipeline should complete without creating new resources; no scrape or ingest spawns for discovery.
- What happens when a resource is stuck in scraping and the recovery run marks it failed? The resource must show a failure reason so operators can decide whether to re-queue.
- What happens when recovery runs while a long-running ingestion is still in progress? Only resources whose last update is older than the stuck threshold are marked failed; recently updated ones are left unchanged.
- How does the system handle duplicate URLs from discovery? Duplicate handling is defined in earlier phases (e.g. skip, no duplicate resource created); orchestration assumes the resources API enforces this.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST run a scheduled discovery process that reads from configured discovery sources, creates or identifies resources for new URLs, and starts the next pipeline stage (scraping) for each new resource.
- **FR-002**: The system MUST chain pipeline stages so that after scraping completes for a resource, ingestion is started for that resource, and after ingestion completes the resource reaches a terminal stage (complete or failed).
- **FR-003**: The system MUST provide a scheduled recovery process that identifies resources stuck in a non-terminal pipeline stage (e.g. scraping or ingesting) for longer than a configurable timeout and marks those resources as failed with a recorded reason (e.g. stuck or timeout).
- **FR-004**: The system MUST NOT perform recovery or cleanup for any separate “jobs” or queue table; recovery applies only to resource pipeline state.
- **FR-005**: The system MUST support manual re-queue of failed resources so that an operator can reset a resource to an early pipeline stage for retry.
- **FR-006**: The system MUST NOT automatically retry failed resources on a schedule; retries are manual only.
- **FR-007**: The system MUST provide a way to trigger discovery in a dry-run mode that reports intended actions without creating or updating resources.
- **FR-008**: The system MUST provide a way to manually trigger scraping for selected or eligible resources (e.g. by stage or identifier).
- **FR-009**: The system MUST provide a way to manually trigger ingestion for selected or eligible resources (e.g. by stage or identifier).
- **FR-010**: Stuck-threshold configuration for recovery MUST be configurable (e.g. separate or shared timeouts for scraping vs ingesting) so that operators can tune sensitivity.

### Key Entities

- **Resource**: The central entity that moves through the pipeline; has a pipeline stage (e.g. discovered, scraping, scraped, ingesting, complete, failed), last-updated time, and optional failure reason. Recovery and re-queue act on resources.
- **Discovery source**: Configured source of URLs (e.g. sitemap, RSS, channel); discovery reads these and creates or matches resources.
- **Pipeline stage**: A discrete state of a resource in the flow from discovery to terminal (complete or failed). Recovery applies to non-terminal stages that have exceeded the stuck timeout.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can run the full pipeline from discovery through ingestion on a schedule and see resources progress to a terminal stage without manual intervention for the normal path.
- **SC-002**: Resources stuck in a non-terminal stage for longer than the configured timeout are marked as failed with a clear reason within one recovery run after the threshold is exceeded.
- **SC-003**: Operators can re-queue a failed resource manually and see it re-enter the pipeline and progress again.
- **SC-004**: Operators can trigger discovery in dry-run mode and see what would be created or processed without side effects.
- **SC-005**: Operators can manually trigger scraping or ingestion for selected resources and observe the expected stage transitions.

## Implementation notes (plan alignment)

- **FR-002 (scrape → ingest):** Implemented by spawning ingest after successful scrape in the scrape Modal worker (see [plan.md](./plan.md) deliverables).
- **FR-003 (recovery):** Implemented by a scheduled Modal function that marks stuck `scraping`/`ingesting` resources as failed using `SCRAPE_STUCK_TIMEOUT_MINUTES` and `INGEST_STUCK_TIMEOUT_MINUTES`.
- **FR-005 (re-queue):** Satisfied by documenting re-queue in the runbook (SQL + Modal re-trigger commands); optional API.
- **FR-010 (timeouts):** Add `SCRAPE_STUCK_TIMEOUT_MINUTES`; remove or repurpose `job_stuck_timeout_minutes` / `JOB_STUCK_TIMEOUT_MINUTES` from config and deploy — job queue has been dropped.

## Assumptions

- Discovery, scraping, and ingestion stages and their APIs or entry points already exist from prior phases; Phase 8 wires them and adds scheduling and resource-pipeline recovery.
- Resource schema includes a pipeline stage, last-updated timestamp, and failure reason so that recovery and re-queue can be implemented.
- Configuration for discovery (e.g. sources, limits) and for recovery (e.g. stuck timeouts) is stored in environment or configuration accessible to the scheduled processes.
- Manual triggers may be exposed via the same mechanism used for scheduled runs (e.g. on-demand invocation) or via an API; the spec does not prescribe the exact surface (API vs CLI) as long as the capabilities are available.
- There is no separate “jobs” table or queue to recover; recovery is solely for resource pipeline state.
