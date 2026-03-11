# Data Model: Content Discovery

## discovery_sources table

Stores each monitored source (sitemap, RSS feed, or YouTube channel) with type, location, filter settings, and enabled flag. Referenced by `resources.discovery_source_id` (optional) for provenance.

### Entity: Discovery source

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| id | UUID | Yes (PK) | Primary key, generated |
| source_type | text | Yes | One of: `sitemap`, `rss`, `youtube_channel` |
| name | text | No | Human-readable label for the source |
| config | JSONB | Yes | Type-specific config (see below) |
| enabled | boolean | Yes | If false, source is skipped by discovery runs. Default true. |
| created_at | timestamptz | Yes | Set on insert |
| updated_at | timestamptz | Yes | Updated on change |
| first_run_at | timestamptz | No | Set after first non–dry_run run that includes this source; NULL = use initial limits on next run |

### config by source_type

- **sitemap**: `{ "url": "<sitemap URL>", "days_back": number?, "require_https": bool?, "required_path_patterns": string[]?, "excluded_path_patterns": string[]?, "max_path_depth": number?, "initial_days_back": number?, "initial_max_urls": number? }` — optional `initial_*` for first-run limits.
- **rss**: `{ "feed_url": "<RSS feed URL>", "days_back": number?, "min_relevance_score": number?, "require_https": bool?, "initial_days_back": number? }` — optional `initial_days_back` for first run.
- **youtube_channel**: `{ "channel_id": "<YouTube channel ID>", "max_videos": number?, "initial_max_videos": number? }` (e.g. 50 for ongoing; optional `initial_max_videos` for first run)

Validation rules:

- `source_type` must be one of the three values.
- For `sitemap`, `config.url` must be present and a valid HTTP(S) URL.
- For `rss`, `config.feed_url` must be present and a valid HTTP(S) URL.
- For `youtube_channel`, `config.channel_id` must be present (non-empty string).
- `days_back`, `max_path_depth`, `min_relevance_score`, `max_videos` when present must be positive numbers.
- `required_path_patterns` / `excluded_path_patterns` when present must be arrays of strings (regex or glob per implementation).

### State

Discovery sources do not have a state machine; they are either enabled or disabled. No transition history required for this phase.

### Relationships

- **resources.discovery_source_id** → **discovery_sources.id** (optional FK). When a resource is created from a discovery run, it may store the source id for provenance. Migration 002 already has `discovery_source_id` on `resources`; ensure FK to `discovery_sources(id)` is added in the discovery_sources migration (or a follow-up) if referential integrity is desired.

---

## Migration

- **File**: `docs/db/migrations/004_discovery_sources.sql`
- **Contents**: Create `discovery_sources` with columns above; unique index not required on (source_type, config) unless we want to prevent duplicate configs; index on `enabled` for listing enabled sources. Optionally add FK from `resources.discovery_source_id` to `discovery_sources(id)`.
- **File**: `docs/db/migrations/005_discovery_first_run_at.sql`
- **Contents**: Add `first_run_at TIMESTAMPTZ NULL` to `discovery_sources` for first-run vs ongoing behavior.

---

## Existing entities (unchanged)

- **resources**: Already has `url`, `pipeline_stage`, `type`, `discovery_source_id`, etc. Discovery creates rows with `pipeline_stage = 'discovered'` and optionally sets `discovery_source_id`. Deduplication is by `url` (unique constraint).
