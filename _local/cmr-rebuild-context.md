# CMR Rebuild — AI-Assisted Development Strategy

## Context

This document summarizes the planning strategy developed for rebuilding the CMR (Content Mining & Research) application. It captures the approach, the tooling decisions, the prompts used, and the current state of the project so work can continue in a new context.

---

## What We're Building

Rebuilding the **CMR (Content Mining & Research)** application — a mining industry content intelligence platform — from a legacy codebase into a modern stack. The goal is to preserve the intent and business logic of the original app while replacing the underlying infrastructure with better tools.

---

## The Two Apps

**App 1 (Legacy)** uses Neon, Celery, Apify, and has accumulated tech debt. Large portions need to be rewritten. The code exists but the architecture needs rethinking.

**App 2 (Modern Starter)** uses Supabase, Modal, FastAPI, and Crawl4AI. The stack is solid and already has auth, jobs, health checks, and Modal worker patterns in place. This becomes the foundation for the rebuild.

---

## The Three-Phase Approach

### Phase 1: Documentation

Extract knowledge from both apps before writing a single line of new code.

**For App 1**, Cursor was used in Agent mode to generate intent-focused domain documentation saved to `/_local/domain_findings/`. These docs capture what each part of the system does, why it exists, and what business logic must be preserved — not how the code works. Output included a domain overview (`overview.md`), per-domain files (in `domains/`), a pain points file, a desired-changes file, and a resource extraction planning doc.

**For App 2**, Cursor was used to generate starter-kit style architecture docs saved to `/_local/starter-kit/`. These docs capture how the modern stack is wired together — patterns, conventions, data layer, auth, Modal jobs, and project structure — written as a blueprint for building new features consistently.

### Phase 2: Build Plan

With both sets of docs in place, Cursor analyzed `/_local/domain_findings/` and `/_local/starter-kit/` together and produced `/_local/build-plan.md` — a dependency-ordered, phased plan for rebuilding the app. The plan has 9 phases, covers stack migration decisions, surfaces open questions per phase, and includes a dependency graph.

### Phase 3: Incremental Specs and Build

Each phase in the build plan maps to one speckit spec, written just-in-time (not all upfront). The rhythm per phase is: resolve open questions → generate spec → build incrementally using Cursor Agent mode.

---

## The Build Plan Summary

| Phase | Name | Complexity | Status |
|-------|------|------------|--------|
| 1 | Foundation — Resources and Auth | Medium | Complete |
| 2 | Scraping — Website (Crawl4AI) | Medium–Large | Complete |
| 2b | Scraping — YouTube (youtube-transcript-api) | Small | Active |
| 3 | Insights — AI Extraction | Large | Active |
| 4 | Knowledge Graph — Graphiti Ingestion | Medium | Active |
| 5 | Content Discovery — Sitemap, RSS, and YouTube | Medium | Active |
| 6 | Trends — Multi-Agent Analysis | — | **Eliminated** |
| 7 | Content Generation | — | **Eliminated** |
| 8 | Pipeline Orchestration and Recovery | Medium | Active |
| 9 | Tasks and Job Monitoring | — | **Eliminated** |

Pipeline flows: Discovery (5) → Scraping (2) → Insights (3) → Knowledge Graph (4), with Orchestration (8) tying it all together. The backend's responsibility ends at Phase 4 — getting clean, structured data into the knowledge graph. Trend analysis and content generation are handled outside the backend by an LLM client connected directly to the Neo4j MCP server.

---

## Terminology

| Term | Definition |
|------|------------|
| **discovery_source** | A monitored source the system checks on a schedule for new content. Has a `source_type`: `sitemap` (XML sitemap URL), `rss` (RSS feed URL), or `youtube_channel` (YouTube channel URL). |
| **resource** | A single piece of content extracted from a discovery source — either a web article URL or a YouTube video URL. The atomic unit of the entire pipeline. |
| **pipeline** | The ordered processing workflow a resource moves through, tracked by `pipeline_stage`: `discovered → scraping → scraped → extracting → extracted → ingesting → complete / failed`. |
| **discovery** | The process of scanning `discovery_sources` to find new URLs and registering them as resources. Upstream of the pipeline — it feeds it. |

## Data Model

**Supabase (Postgres) — operational layer**

| Table | Purpose |
|-------|---------|
| `discovery_sources` | Sources to monitor — sitemaps, RSS feeds, YouTube channels |
| `resources` | Content units with full pipeline lifecycle, scraped content, and insight data |
| `jobs` | Modal job tracking (exists in starter) |

**Neo4j — intelligence layer**

The knowledge graph built from ingested insights. Entities, relationships, and facts extracted from resources. This is what the LLM client queries via MCP.

---

## Key Stack Migration Decisions

| Concern | Legacy | New |
|---------|--------|-----|
| Database | Neon | Supabase |
| Task queue | Celery + Redis | Modal |
| Scraping | Apify (external, polled) | Crawl4AI (direct, in-process) |
| Pipeline state | Dual status columns | Single `pipeline_stage` |
| Orchestration | 5 independent cron jobs | Modal scheduled + chained calls |
| Observability | Logfire | Sentry |

---

## Resolved Decisions

| Decision | Resolution |
|----------|------------|
| **Auth model** | Supabase JWT as-is. No API key system. Cron and Modal functions use a service account JWT stored as a Modal secret. |
| **Pipeline state** | Single `pipeline_stage` column on `resource`. Values: `discovered`, `scraping`, `scraped`, `extracting`, `extracted`, `ingesting`, `complete`, `failed`. Introduced in Phase 1. |
| **`scrape` flag** | Dropped. Eligibility derived from `pipeline_stage` (`discovered` = eligible). |
| **Crawl4AI usage** | Python library, running inside the existing `browser` tier Modal function. |
| **Raw content storage** | JSONB column on the `resource` row. |
| **Scrape trigger** | No manual trigger endpoint. Modal function invoked directly via CLI/dashboard or spawned by discovery. |
| **Alignment score** | Omitted. Never implemented in legacy; not needed. |
| **Retry strategy** | Modal-level retries only. No retry logic inside agents. |
| **Model config** | Per-task env vars: `MODEL_INSIGHT_EXTRACTION`, `MODEL_TRENDS` (n/a), `MODEL_CONTENT_GENERATION` (n/a), `MODEL_FACT_CHECK` (n/a). |
| **Neo4j hosting** | Neo4j Aura. Env vars: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Add to Modal secrets. |
| **Episode length** | Phase 3 agent produces atomic outputs naturally. Phase 4 adds `MAX_EPISODE_LENGTH` env var (default 500 chars) as a safety net. |
| **Discovery sources config** | Stored in a `discovery_sources` Supabase table with `source_type` column: `sitemap`, `rss`, `youtube_channel`. Replaces legacy flat file. Migration script in Phase 5. |
| **Discovery → scrape handoff** | Batch: collect all new resources, deduplicate, then spawn scrape jobs for net-new only. |
| **Failed resource retry** | Manual re-queue only. `failure_reason` stored on resource record (error type + message). No automatic retries — blocked sites would loop forever. |
| **Cleanup tasks** | Removed. Never implemented in legacy; no equivalent in Modal architecture. |
| **Job cancellation** | Not needed via API. Modal timeouts handle runaway jobs; manual cancellation available via Modal dashboard. |
| **Trends system** | **Eliminated from backend.** Replaced by LLM client connected directly to Neo4j MCP server. |
| **Content generation** | **Eliminated from backend.** Handled by the same LLM client via Neo4j MCP. |
| **Jobs API (Phase 9)** | **Eliminated.** Starter's existing `GET /jobs` and `GET /jobs/{id}` are sufficient as-is. |

---

## Folder Structure

```
/_local/
  domain_findings/                         # App 1 intent/domain documentation (generated)
    overview.md                        # High-level app summary and domain index
    pain-points.md                     # Tech debt, inconsistencies, ambiguities
    desired-changes.md                 # Intent-only notes on changes to pursue later
    resource_extraction_planning.md    # Redesign planning for the extraction pipeline
    domains/                           # Per-domain files (one per feature area)
      01-resources.md
      02-scraping.md
      03-insights.md
      04-knowledge-graph.md
      05-trends.md
      06-content-generation.md
      07-authentication.md
      08-content-discovery.md
      09-scheduled-pipeline.md
      10-tasks.md
  starter-kit/                         # App 2 architectural blueprint docs (generated)
    README.md                          # Index of starter-kit docs
    overview.md                        # Stack inventory and high-level wiring
    project-structure.md               # Directory tree and naming conventions
    data-layer.md                      # DB connection, ORM patterns, migrations
    auth.md                            # Auth implementation end to end
    stack-wiring.md                    # Bootstrap, env config, async patterns
    modal-jobs.md                      # Modal job lifecycle and conventions
    patterns.md                        # Reusable patterns and conventions
    starter-expectations.md            # First-run checklist / validation guide
  build-plan.md                        # Phased rebuild plan (generated)
  specs/                               # One folder per phase spec (to be created)
```

---

## Tooling

- **Cursor** in Agent mode for all documentation generation and spec work
- **Speckit** for per-phase specs — one spec folder per phase, written just-in-time
- All prompts were run against the live codebase with Cursor having full file access

---

## Prompts Used

### App 1 — Domain Documentation Prompt
Run in Cursor Agent mode against the legacy codebase. Generates intent-focused domain docs to `/_local/domain_findings/`.

```
You are a technical documentation assistant. Your job is to analyze this codebase and produce a set of intent-focused domain documentation files. The goal is NOT to document the code itself — it is to capture what the application does, why each part exists, and what problems it solves. This documentation will be used to inform a future rewrite, so focus on behavior, purpose, and business logic over implementation details.

Do the following:

1. **Start with a high-level survey.** Explore the codebase structure — routes, models, services, components, config files, etc. Get a feel for the full shape of the app before writing anything.

2. **Identify the core domains.** Group the application into logical domains or feature areas (e.g. authentication, user management, data processing, reporting, etc.). List these domains and confirm your understanding before proceeding.

3. **For each domain, create a markdown file** saved to a `/_local/domain_findings/` folder. Each file should cover:
   - **Purpose** — What is this domain responsible for? Why does it exist?
   - **Core behavior** — What does it actually do? Walk through the key flows and logic in plain language.
   - **Key data** — What data does it work with? What are the important entities, fields, or states?
   - **Boundaries** — What does this domain depend on? What depends on it?
   - **Edge cases and notable logic** — Any non-obvious rules, special handling, or gotchas baked into the code.
   - **What to preserve** — Based on what you see, what intent or behavior seems important to carry forward in a rewrite?

4. **Create a root overview file** at `/_local/domain_findings/overview.md` that covers:
   - What the application does at a high level
   - The full list of identified domains with a one-line summary of each
   - The overall data flow or architecture in plain language
   - Tech stack inventory (frameworks, key libraries, database, APIs, etc.)
   - Any patterns or conventions used throughout the codebase

5. **Create a pain points file** at `/_local/domain_findings/pain-points.md` that captures:
   - Areas of the code that appear overly complex, inconsistent, or hard to follow
   - Any patterns that seem like they were workarounds or tech debt
   - Places where the intent is unclear even after reading the code

Do not rush. Prioritize accuracy and clarity over speed. If something is ambiguous, note the ambiguity in the doc rather than guessing. Write as if the reader is a developer who has never seen this codebase but needs to rebuild it from scratch.
```

---

### App 2 — Starter Kit Architecture Prompt
Run in Cursor Agent mode against the modern starter codebase. Generates architectural blueprint docs to `/_local/starter-kit/`.

```
You are a technical documentation assistant. Your job is to analyze this codebase and produce a set of "starter kit" style architecture documents. The goal is to capture how this app is built — its patterns, conventions, and wiring — clearly enough that a developer could use these docs as a blueprint to build a brand new app from scratch using the same stack and approach.

Do not document features or business logic. Focus entirely on structure, patterns, and how things are connected.

Do the following:

1. **Start with a full survey of the codebase.** Explore the project structure, config files, dependencies, middleware, and entry points before writing anything. Understand how the pieces connect before documenting them.

2. **Create a `/_local/starter-kit/` folder** and save all output there.

3. **Create `/_local/starter-kit/overview.md`** covering:
   - Full tech stack inventory (framework, database, auth, hosting, key libraries, tooling)
   - How the stack pieces connect to each other at a high level
   - Any notable architectural decisions or patterns used throughout

4. **Create `/_local/starter-kit/project-structure.md`** covering:
   - A commented directory tree of the project
   - The purpose of each major folder and file type
   - Any naming conventions or organizational patterns used
   - Where to find key things (routes, components, DB logic, config, etc.)

5. **Create `/_local/starter-kit/data-layer.md`** covering:
   - How the database is connected and configured
   - ORM or query patterns used
   - How migrations are handled
   - How data models are defined and where they live
   - Any conventions for structuring queries or database access

6. **Create `/_local/starter-kit/auth.md`** covering:
   - How authentication is implemented end to end
   - Middleware and route protection patterns
   - Session or token management
   - Any role or permission handling

7. **Create `/_local/starter-kit/stack-wiring.md`** covering:
   - How the app bootstraps and initializes
   - How environment config is loaded and used
   - How the frontend and backend communicate (if applicable)
   - Any background jobs, queues, or async patterns
   - How external services or APIs are integrated

8. **Create `/_local/starter-kit/modal-jobs.md`** covering:
   - How Modal is configured and initialized in this project
   - How Modal functions/jobs are defined — decorators, resource configuration, environment setup
   - The full lifecycle of a job from trigger to completion
   - The API endpoint that kicks off jobs — its route, payload, how it invokes Modal, and any validation or pre-processing that happens before the job is dispatched
   - The API endpoint that checks for orphaned jobs — its route, what defines an "orphaned" job, how it detects them, and what it does when it finds one
   - How job state is tracked and persisted (what's stored, where, and when)
   - Any retry logic, error handling, or failure states
   - How to add a new Modal job following the existing pattern

9. **Create `/_local/starter-kit/patterns.md`** covering:
   - Reusable patterns and conventions used throughout the codebase
   - How new features are typically added (the "shape" of adding something new)
   - Any abstractions, utilities, or shared logic worth reusing
   - Code style or structural conventions a new developer should follow

Write everything as if you are producing a reference guide for a developer starting a new project with this same stack. Be specific and concrete — use file paths, function names, and real examples from the codebase to illustrate each point. If something is ambiguous or inconsistently implemented, note it.
```

---

### Build Plan Prompt
Run in Cursor Agent mode with access to both `/_local/domain_findings/` and `/_local/starter-kit/`. Generates `/_local/build-plan.md`.

```
You are a technical planning assistant. Your job is to analyze the existing domain documentation for a legacy application and produce a phased build plan for rebuilding it as a new application using a modern starter kit.

You have access to two sets of documents:
- `/_local/domain_findings/` — domain documentation for the legacy app, describing what each part of the system does, its intent, and its business logic
- `/_local/starter-kit/` — architecture documentation for the new starter app, describing its stack, patterns, and conventions

Do the following:

1. **Read all files in `/_local/domain_findings/`** thoroughly before proceeding. Understand the full scope of the legacy app — every domain, every feature area, every major piece of functionality.

2. **Read all files in `/_local/starter-kit/`** to understand what already exists in the new app — the stack, patterns, data layer, auth, and Modal job conventions.

3. **Identify all domains and feature areas** that need to be rebuilt. For each one, note:
   - What it does
   - What it depends on (other domains or data that must exist first)
   - Rough complexity (small / medium / large)

4. **Produce a dependency-ordered build sequence.** Things with no dependencies come first. Things that depend on other domains come after. Flag any circular dependencies or ambiguities.

5. **Create `/_local/build-plan.md`** structured as follows:

   - **Overview** — a short paragraph describing the full scope of the rebuild at a high level
   - **What exists in the starter** — a summary of what is already in place and does not need to be built
   - **Stack changes to keep in mind** — note any infrastructure differences between the legacy app and the new stack (e.g. different job system, different database) that will affect how domains are rebuilt
   - **Phases** — one section per phase, each containing:
     - Phase number and name
     - What is being built in this phase
     - Why it comes at this point in the sequence (what it enables or depends on)
     - The domains or features included
     - Rough complexity and estimated scope
     - Any open questions or decisions that need to be made before or during this phase
   - **Deferred or out of scope** — anything from the legacy app that should not be rebuilt, is low priority, or needs a separate decision before including

Write the plan as if it will be handed to a developer who will use it to write one speckit spec per phase, building the app incrementally. Be specific, honest about complexity, and flag anything ambiguous rather than glossing over it.
```

---

## Current Status

**The build plan has been fully audited and all open questions resolved.** Every decision is annotated directly in `/_local/build-plan.md`. The plan is locked and ready for spec generation.

Key outcomes from the audit:
- Phases 6 (Trends), 7 (Content Generation), and 9 (Tasks) were **eliminated** — these concerns move outside the backend to an LLM client with Neo4j MCP access
- The backend's responsibility ends at Phase 4: getting clean, structured data into the knowledge graph
- The active build sequence is: **Phase 1 → 2 → 3 → 4 → 5 → 8**
- All architectural decisions are resolved (see Resolved Decisions table above)

---

## Next Step: Generate Specs and Build

The build plan is locked. For each active phase, the rhythm is:

1. **Generate the spec** using a prompt that references:
   - The relevant phase section from `/_local/build-plan.md`
   - The relevant domain file(s) from `/_local/domain_findings/domains/`
   - `/_local/starter-kit/patterns.md`
2. **Build task by task** in Cursor Agent mode using the spec as a checklist
3. **Update `/_local/build-plan.md`** if scope or sequencing changes during the build

Active phases in order: **1 → 2 → 3 → 4 → 5 → 8**

Start with Phase 1: Foundation — Resources and Auth.