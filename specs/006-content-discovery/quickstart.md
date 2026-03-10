# Quickstart: Content Discovery (Phase 5)

Get discovery running locally and verify behavior without blocking the main 10-minute app setup.

## Prerequisites

- Repo and app already runnable (Phase 1–4): `uv sync`, `.env` with Supabase and optional Neo4j/OpenAI for ingestion.
- Optional: `YOUTUBE_API_KEY` in `.env` (and in Modal secrets for deployed discovery) if you add a YouTube channel source.

## 1. Apply migration

Run the discovery_sources migration so the table exists:

```bash
# From repo root; adjust if your project uses a different migration runner
psql "$DATABASE_URL" -f docs/db/migrations/004_discovery_sources.sql
```

Or apply via Supabase dashboard SQL editor using the contents of `004_discovery_sources.sql`.

## 2. Add at least one source

Insert a row (or use a future admin/API if added). Example for a sitemap:

```sql
INSERT INTO discovery_sources (id, source_type, name, config, enabled)
VALUES (
  gen_random_uuid(),
  'sitemap',
  'Example sitemap',
  '{"url": "https://example.com/sitemap.xml", "days_back": 7, "require_https": true}'::jsonb,
  true
);
```

Example for RSS:

```sql
INSERT INTO discovery_sources (id, source_type, name, config, enabled)
VALUES (
  gen_random_uuid(),
  'rss',
  'Example RSS',
  '{"feed_url": "https://example.com/feed.xml", "days_back": 14}'::jsonb,
  true
);
```

Example for YouTube (requires `YOUTUBE_API_KEY`):

```sql
INSERT INTO discovery_sources (id, source_type, name, config, enabled)
VALUES (
  gen_random_uuid(),
  'youtube_channel',
  'Example channel',
  '{"channel_id": "UCxxxxxx", "max_videos": 20}'::jsonb,
  true
);
```

## 3. Run discovery in dry-run

Verify that discovery reads sources and reports what it would do, without creating resources or spawning scrape:

```bash
modal run src.deployment.modal_workers::run_discovery --dry-run
```

Check logs: you should see per-source fetch/filter results and a summary like “would submit N URLs” with no resources created.

## 4. Run discovery for real

```bash
modal run src.deployment.modal_workers::run_discovery
```

- In Supabase, confirm new rows in `resources` with `pipeline_stage = 'discovered'` and URLs matching the sources.
- Confirm scrape jobs were spawned (e.g. Modal dashboard or logs showing `scrape_resource.spawn(...)` for each new resource id).

## 5. Idempotency

Run discovery again with the same sources. There should be no duplicate `resources` rows for the same URL; new resources count should be 0 (or only for newly appeared URLs in the source).

## Troubleshooting

- **No sources run**: Ensure rows in `discovery_sources` have `enabled = true` and `source_type` in `sitemap`, `rss`, `youtube_channel`.
- **YouTube errors**: Ensure `YOUTUBE_API_KEY` is set in the environment used by the Modal function (e.g. Modal secret).
- **Sitemap/RSS timeout or 5xx**: One failing source should not stop others; check logs for which source failed and fix URL or network.
