# CMR Rebuild — Spec Planning Prompts

One prompt per active phase. Run each prompt in Cursor Agent mode using spec-kit.
Save output to `_local/specs/0{N}-{phase-name}/`.

Active build sequence: **Phase 1 → 2 → 2b → 4 → 5 → 8**. Phase 3 (Insights) is superseded: Graphiti is the single extractor; Phase 4 implements ingestion from scraped content and removes the Phase 3 extraction code. Prompts below for Phase 3 are for reference only; Phase 4 is the next spec to generate/refine.

---

## Phase 1: Foundation — Resources and Auth

```
Read the following files before creating the spec for Phase 1 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/01-resources.md — for the legacy business logic and edge cases to preserve
- @_local/domain_findings/domains/07-authentication.md — for auth context
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/data-layer.md — for database conventions and migration patterns
- @_local/starter-kit/auth.md — for how auth is wired in the starter

Create a spec for Phase 1: Foundation — Resources and Auth only. Do not plan beyond this phase.
```

---

## Phase 2: Scraping — Crawl4AI Integration

```
Read the following files before creating the spec for Phase 2 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/02-scraping.md — for the legacy scraping logic and edge cases to preserve
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal worker conventions and browser tier setup

Create a spec for Phase 2: Scraping — Crawl4AI Integration only. Do not plan beyond this phase.
```

---

## Phase 2b: YouTube Scraping

```
Read the following files before creating the spec for Phase 2b only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/02-scraping.md — for the legacy YouTube handling logic to preserve
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal worker conventions
- @specs/003-scraping/ — for the existing website scraping pattern this phase extends

Phase 2b extends the existing `scrape_resource` Modal function to handle `type = youtube` resources using `youtube-transcript-api`. Crawl4AI does not support YouTube. The extraction path, `scraped_content` JSONB schema, `pipeline_stage` transitions, and failure handling are identical to Phase 2 — only the extraction library differs. No new tables, no new Modal functions.

Create a spec for Phase 2b: YouTube Scraping only. Do not plan beyond this phase.
```

---

## Phase 3: Insights — Superseded (reference only)

Phase 3 as originally scoped (PydanticAI extraction agent, `insight` JSONB) is **superseded**. Graphiti is the single extractor; ingestion reads **scraped content** and sends it to Graphiti (Phase 4). No new Phase 3 spec is required. The existing `specs/004-insights/` folder is historical; Phase 4 implementation will remove the Phase 3 extraction code. See build-plan.md Phase 3 and Phase 4 sections.

---

## Phase 4: Knowledge Graph — Graphiti Ingestion (from scraped content)

```
Read the following files before creating the spec for Phase 4 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist (Phase 4 and Phase 3 superseded)
- @_local/domain_findings/domains/04-knowledge-graph.md — for the legacy Graphiti ingestion logic and edge cases to preserve
- @_local/domain_findings/domains/03-insights.md — for legacy context (extraction intent; Graphiti now does this)
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal worker conventions
- Graphiti docs / examples: https://github.com/getzep/graphiti — add_episode (or equivalent) API for ingesting text; Graphiti performs LLM extraction, entity merge, temporal edges

Phase 4 scope:
1. **Ingestion worker:** Modal function that accepts resource_id, fetches resource and scraped_content (markdown, url, title), validates (e.g. min word count), transitions to ingesting, calls Graphiti to add episode(s) from the scraped text, then sets pipeline_stage = complete or failed. Pipeline is scraped → ingesting → complete (no extracting/extracted).
2. **Removal of Phase 3 extraction code:** As part of Phase 4, remove the PydanticAI insight agent, InsightsService.extract_insights, extract_insights Modal function, DAO methods used only for extraction, insight-related models/config, and update runbook. Optionally deprecate or ignore the insight column on resources.

Graphiti is the single extractor: it receives scraped text and performs entity/relationship extraction and merge; the existing Neo4j graph (Entity by name, RELATES_TO, Episodic, MENTIONS) was built this way. Ensure the spec covers Graphiti client setup (Neo4j env vars in Modal secrets), episode format (text + optional metadata), and failure handling (failure_reason, stuck ingesting recovery in Phase 8).

Create a spec for Phase 4: Knowledge Graph — Graphiti Ingestion from scraped content only. Do not plan beyond this phase.
```

---

## Phase 5: Content Discovery — Sitemap, RSS, and YouTube

```
Read the following files before creating the spec for Phase 5 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/08-content-discovery.md — for the legacy discovery logic and edge cases to preserve
- @_local/domain_findings/domains/09-scheduled-pipeline.md — for the legacy scheduling and orchestration context
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal scheduled function conventions
- @_local/starter-kit/data-layer.md — for migration patterns (discovery_sources table)

Discovery has three source types tracked in the `discovery_sources` table (`source_type`: `sitemap`, `rss`, `youtube_channel`). Each produces resources (web article URLs or YouTube video URLs) that enter the pipeline at `pipeline_stage = discovered`.

Create a spec for Phase 5: Content Discovery — Sitemap, RSS, and YouTube only. Do not plan beyond this phase.
```

---

## Phase 8: Pipeline Orchestration and Recovery

```
Read the following files before creating the spec for Phase 8 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/09-scheduled-pipeline.md — for the legacy orchestration and recovery logic to preserve
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal scheduled function and recovery worker conventions
- @_local/starter-kit/stack-wiring.md — for how the app bootstraps and how async patterns are wired

Create a spec for Phase 8: Pipeline Orchestration and Recovery only. Do not plan beyond this phase.
```