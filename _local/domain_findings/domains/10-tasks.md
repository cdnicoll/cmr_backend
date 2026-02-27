# Domain: Tasks (Celery)

## Purpose

The Tasks domain exposes **generic Celery task operations** — triggering sample tasks, checking status, listing active tasks, and cancelling running tasks. It is a thin wrapper over Celery's AsyncResult and control APIs.

## Core Behavior

1. **Trigger hello task** (`POST /api/v1/tasks/hello`): Queues `hello_world.delay()`, returns task_id
2. **Get task status** (`GET /api/v1/tasks/{task_id}/status`): Returns Celery AsyncResult status, result if ready, progress if running
3. **List active tasks** (`GET /api/v1/tasks`): Returns `inspect.active()` — tasks currently running on workers
4. **Cancel task** (`DELETE /api/v1/tasks/{task_id}`): Revokes task with `terminate=True, signal=SIGKILL`

## Key Data

- **TaskResponse**: task_id, status, message
- **Status response**: task_id, status, ready, result (if done), error (if failed), progress (if running)

## Boundaries

- **Depends on**: Celery app, Redis (broker/backend)
- **Depended on by**: None (utility for debugging/monitoring)

## Edge Cases and Notable Logic

- **PENDING + no info**: Could be new or non-existent task; revoke attempted anyway
- **Already completed**: Cancel returns 200 with status "ALREADY_COMPLETED"
- **Task IDs**: Insight/graphiti/content endpoints return their own task IDs; this API works with any Celery task_id

## What to Preserve

- Generic task status/result access pattern
- Cancel with terminate for running tasks
