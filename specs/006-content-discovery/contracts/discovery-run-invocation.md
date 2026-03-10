# Contract: Discovery run invocation

Discovery is invoked as a Modal function. It does not expose an HTTP API; operators trigger it via Modal dashboard/CLI or via its schedule.

## Scheduled run

- **Function**: `run_discovery` (or equivalent name in `modal_workers.py`)
- **Schedule**: e.g. `modal.Period(days=1)` (daily). Exact cadence is deployment/config choice.
- **Arguments**: None for scheduled invocation.
- **Behavior**: Load all enabled discovery sources, run sitemap/RSS/YouTube scanners, filter and deduplicate, submit net-new URLs to resource creation, spawn scrape for created resource IDs. Not dry-run.

## Manual / CLI run

- **Invocation**: `modal run src.deployment.modal_workers::run_discovery [--dry-run]`
- **Parameters**:
  - `dry_run` (optional, default false): When true, perform all fetch/filter/dedupe steps but do not create resources and do not spawn scrape; report what would have been submitted (e.g. counts per source, sample URLs).
- **Behavior**: Same as scheduled run when `dry_run` is false; when true, no side effects, only logs/summary.

## Output / observability

- Logs: Per-source success/failure; total URLs collected, filtered, submitted; count of resources created and scrape jobs spawned.
- Dry-run: Same logs up to “would submit” plus explicit “DRY RUN: no resources created, no scrape spawned”.
- No return value contract for callers; success/failure is via exit code and logs.
