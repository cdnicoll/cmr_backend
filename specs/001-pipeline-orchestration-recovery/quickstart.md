# Quickstart: Pipeline Orchestration and Recovery

After implementing Phase 8, use this to verify the full pipeline and recovery.

## Prerequisites

- Discovery sources configured and migration applied (see main runbook).
- Modal workers deployed (`uv run deploy_dev` or `deploy_prod`).

## 1. Full pipeline (discovery → scrape → ingest)

1. Run discovery (dry-run first):
   ```bash
   modal run src.deployment.modal_workers::run_discovery --dry-run
   modal run src.deployment.modal_workers::run_discovery
   ```
2. Check Supabase: new resources with `pipeline_stage = discovered`; scrape jobs spawn automatically.
3. After scrape completes, ingest should spawn automatically for each scraped resource.
4. Verify resources move to `scraped` then `ingesting` then `complete` (or `failed`). Check Neo4j for completed resources.

## 2. Resource-pipeline recovery (stuck → failed)

1. In Supabase, set a resource to `pipeline_stage = 'scraping'` and set `updated_at` to a time older than `SCRAPE_STUCK_TIMEOUT_MINUTES` (e.g. 20 minutes ago).
2. Run recovery (or wait for the scheduled run):
   ```bash
   modal run src.deployment.modal_workers::run_recovery_pipeline
   ```
3. Verify that resource now has `pipeline_stage = 'failed'` and `failure_reason` indicates stuck/timeout.
4. Repeat for a resource in `ingesting` with old `updated_at`; recovery should mark it failed with ingest timeout reason.

## 3. Manual re-queue (failed → discovered)

1. Pick a resource with `pipeline_stage = 'failed'`.
2. Re-queue via API (if implemented):
   ```bash
   curl -X POST "http://localhost:8000/api/v1/resources/<resource-id>/requeue" \
     -H "Authorization: Bearer $JWT_TOKEN"
   ```
   Or via runbook/SQL as documented in main runbook.
3. Verify the resource has `pipeline_stage = 'discovered'` and `failure_reason` is null. Trigger scrape (or wait for next discovery batch) to confirm it re-enters the pipeline.

## 4. Manual triggers (existing)

- **Discovery (dry-run)**: `modal run src.deployment.modal_workers::run_discovery --dry-run`
- **Scrape one resource**: `modal run src.deployment.modal_workers::scrape_resource --resource-id "<uuid>"`
- **Ingest one resource**: `modal run src.deployment.modal_workers::ingest_resource --resource-id "<uuid>"`

See main runbook for full commands and verification queries.
