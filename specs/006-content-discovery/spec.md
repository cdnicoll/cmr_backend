# Feature Specification: Phase 5 — Content Discovery (Sitemap, RSS, YouTube)

**Feature Branch**: `006-content-discovery`  
**Created**: 2025-03-08  
**Status**: Draft  
**Input**: User description: "Phase 5: Content Discovery — Sitemap, RSS, and YouTube only. Do not plan beyond this phase."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily automated discovery of new content (Priority: P1)

The system runs a scheduled discovery process that reads all configured sources (sitemaps, RSS feeds, and YouTube channels), collects candidate URLs, filters them by date and relevance, deduplicates against existing content, and creates new resource records for net-new URLs. Each new resource enters the pipeline in a "discovered" state so it can be scraped and ingested later.

**Why this priority**: Discovery is the entry point that feeds the rest of the pipeline; without it, no new content is added automatically.

**Independent Test**: Run the discovery process once with at least one source of each type configured; verify new resources appear with "discovered" status and duplicate URLs are not created when run again.

**Acceptance Scenarios**:

1. **Given** at least one enabled sitemap source, **When** the scheduled discovery runs, **Then** URLs from that sitemap are parsed, filtered, and submitted as new resources with "discovered" status.
2. **Given** at least one enabled RSS source, **When** the scheduled discovery runs, **Then** feed entries are parsed, filtered, and submitted as new resources with "discovered" status.
3. **Given** at least one enabled YouTube channel source, **When** the scheduled discovery runs, **Then** video URLs from that channel are collected and submitted as new resources with "discovered" status.
4. **Given** the same discovery run is executed a second time with no new items from sources, **When** discovery runs, **Then** no duplicate resource records are created for URLs that already exist.
5. **Given** discovery has just created new resources, **When** the same run completes, **Then** scraping is triggered only for those net-new resources (not for ones that already existed).

---

### User Story 2 - Operators configure and manage discovery sources (Priority: P2)

Operators can add, update, and manage the list of monitored sources (sitemaps, RSS feeds, YouTube channels) without redeploying the application. Each source has a type and configuration that controls which URLs are considered (e.g. how far back in time to look, relevance thresholds, path rules). Sources can be enabled or disabled.

**Why this priority**: Configurable sources allow the business to add new publishers or adjust coverage without code changes.

**Independent Test**: Add one source of each type (sitemap, RSS, YouTube channel) and run discovery; confirm each source is read and produces the expected kind of URLs.

**Acceptance Scenarios**:

1. **Given** an operator adds a new sitemap source with a URL and optional filters, **When** discovery runs, **Then** that sitemap is fetched and its URLs are processed according to the source's filter settings.
2. **Given** an operator adds an RSS source with a feed URL, **When** discovery runs, **Then** that feed is parsed and its entries are processed according to the source's filter settings.
3. **Given** an operator adds a YouTube channel source with a channel identifier, **When** discovery runs, **Then** that channel's recent videos are collected and submitted as resources.
4. **Given** a source is disabled, **When** discovery runs, **Then** that source is skipped and no URLs from it are submitted.

---

### User Story 3 - Safe testing with dry-run (Priority: P3)

Operators can run discovery in a dry-run mode that performs all reading and filtering but does not create resources or trigger scraping. This allows validating source configuration and filter behavior without affecting the pipeline.

**Why this priority**: Reduces risk when adding new sources or changing filters; operators can verify behavior before going live.

**Independent Test**: Run discovery in dry-run mode with one or more sources; confirm no new resources are created and no scrape jobs are triggered, while logs or output indicate what would have been submitted.

**Acceptance Scenarios**:

1. **Given** discovery is invoked in dry-run mode, **When** it runs against configured sources, **Then** no new resource records are created and no scrape work is triggered.
2. **Given** dry-run mode, **When** discovery runs, **Then** the system reports what URLs would have been submitted (e.g. count and source breakdown) so operators can verify filters and sources.

---

### Edge Cases

- What happens when a sitemap or RSS feed is temporarily unreachable (timeout, 5xx)? Discovery continues with other sources; the failing source is reported so operators can investigate. No partial state is left for that source.
- What happens when a source returns no URLs (empty feed, sitemap with no matching entries)? The run completes successfully for that source with zero new resources; no error.
- What happens when the same URL appears in multiple sources? After deduplication, only one resource is created; duplicate URLs are skipped on submit.
- What happens when URL filtering removes all candidates for a source (e.g. everything too old or below relevance)? No resources are created for that source; discovery continues.
- What happens when a YouTube channel has no recent videos or the channel is invalid? Discovery handles the channel without failing the entire run; invalid or empty channels are reported and no resources created for that source.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store and manage a list of discovery sources, each with a type (sitemap, RSS, or YouTube channel) and configuration needed to fetch and filter URLs.
- **FR-002**: The system MUST support a sitemap scanner that fetches sitemap XML, parses URLs, and applies configurable filters (e.g. date range, path patterns, HTTPS requirement) before deduplication and submission.
- **FR-003**: The system MUST support an RSS scanner that fetches configured RSS feeds, parses entries, and applies configurable filters (e.g. date range, relevance) before deduplication and submission. Auto-discovery of feed URLs from web pages is out of scope; feeds must be explicitly configured.
- **FR-004**: The system MUST support a YouTube channel scanner that fetches recent videos for configured channels and submits video URLs as resources.
- **FR-005**: The system MUST run discovery on a defined schedule (e.g. daily) so that new content from all enabled sources is collected without manual intervention.
- **FR-006**: The system MUST deduplicate candidate URLs against existing resources so that a given URL results in at most one resource record; duplicate URLs MUST be skipped on submit (no error, no duplicate rows).
- **FR-007**: The system MUST submit only net-new URLs to the resource creation endpoint so that each new resource is created with initial pipeline status "discovered."
- **FR-008**: The system MUST trigger scraping only for resources that were newly created in that discovery run (net-new); it MUST NOT re-trigger scrape for resources that already existed.
- **FR-009**: The system MUST support configurable URL filtering per source or globally, including at least: limit by age (e.g. days back), minimum relevance score when applicable, path inclusion/exclusion rules, and requirement that URLs use HTTPS where applicable.
- **FR-010**: The system MUST support a dry-run mode that performs all source reading and filtering and reports what would be submitted, without creating resources or triggering scraping.
- **FR-011**: When a single source fails (e.g. unreachable, parse error), the system MUST continue processing other sources and MUST report the failure so operators can act; the run MUST NOT abort entirely for one bad source.
- **FR-012**: The system MUST authenticate to the resource creation and scrape-trigger endpoints using the same mechanism as other automated callers (e.g. service account) so discovery can run unattended.

### Key Entities

- **Discovery source**: A monitored origin of content URLs. Has a type (sitemap, rss, youtube_channel), configuration (URLs, channel identifier, filter settings such as days back, relevance threshold, path patterns), and enabled/disabled state. Stored so operators can add or change sources without redeploying.
- **Resource**: The existing entity representing a single content item (e.g. article or video) by URL. Discovery creates new resources with initial pipeline status "discovered"; each URL corresponds to at most one resource after deduplication.
- **Discovery run**: A single execution of the discovery process: read all enabled sources, filter and deduplicate URLs, create net-new resources, then trigger scraping for those net-new resources only. Can be run on a schedule or manually; supports dry-run.

## Assumptions

- The resource creation endpoint and scrape-trigger mechanism already exist and accept batch or per-URL submission; discovery will use them as defined in earlier phases.
- Pipeline status "discovered" is the correct initial state for new resources; downstream stages (scrape, ingest) are out of scope for this phase.
- RSS auto-discovery (finding feed URLs from a website) is explicitly out of scope; only explicitly configured RSS feed URLs are used.
- Filter defaults (e.g. default days back, default batch size) follow legacy behavior where documented; otherwise reasonable defaults are used (e.g. 7–30 days back).
- The schedule for discovery (e.g. daily) is configurable at deployment or via configuration; exact cadence is an operational choice.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can add or update a discovery source and see it used on the next scheduled run without redeploying the application.
- **SC-002**: A single discovery run completes successfully when at least one source is reachable; failure of one source does not prevent other sources from being processed.
- **SC-003**: Duplicate URLs never create duplicate resource records; re-running discovery with the same source data does not create new resources for URLs that already exist.
- **SC-004**: All new resources created by discovery enter the pipeline in "discovered" status and are eligible for scraping; scraping is triggered only for those net-new resources in that run.
- **SC-005**: Dry-run mode produces no new resources and no scrape triggers, while still reporting what would have been submitted so operators can validate configuration.
- **SC-006**: Discovery supports all three source types (sitemap, RSS, YouTube channel) with filtering and deduplication applied consistently so that only relevant, net-new URLs become resources.
