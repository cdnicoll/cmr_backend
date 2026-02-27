# CMR Rebuild — Spec Planning Prompts

One prompt per active phase. Run each prompt in Cursor Agent mode using spec-kit.
Save output to `_local/specs/0{N}-{phase-name}/`.

Active build sequence: **Phase 1 → 2 → 3 → 4 → 5 → 8**

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

## Phase 3: Insights — AI Extraction

```
Read the following files before creating the spec for Phase 3 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/03-insights.md — for the legacy insight extraction logic and edge cases to preserve
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal worker conventions

Create a spec for Phase 3: Insights — AI Extraction only. Do not plan beyond this phase.
```

---

## Phase 4: Knowledge Graph — Graphiti Ingestion

```
Read the following files before creating the spec for Phase 4 only:

- @_local/build-plan.md — for the phase scope, decisions, and test checklist
- @_local/domain_findings/domains/04-knowledge-graph.md — for the legacy Graphiti ingestion logic and edge cases to preserve
- @_local/starter-kit/patterns.md — for how new features are structured in this codebase
- @_local/starter-kit/modal-jobs.md — for the Modal worker conventions

Create a spec for Phase 4: Knowledge Graph — Graphiti Ingestion only. Do not plan beyond this phase.
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