# Starter Kit — Architecture Documentation

This folder contains architecture documentation for this application. Use these docs as a blueprint to build a new app with the same stack and approach.

**Focus**: Structure, patterns, and wiring — not business logic or features.

---

## Documents

| Document | Contents |
|----------|----------|
| [starter-expectations.md](starter-expectations.md) | **First-run expectations** — health check, sample worker, job API, recovery endpoint, migration script |
| [overview.md](overview.md) | Tech stack, how pieces connect, architectural decisions |
| [project-structure.md](project-structure.md) | Directory tree, folder purposes, naming conventions |
| [data-layer.md](data-layer.md) | Database connections, Supabase vs asyncpg, migrations, models |
| [auth.md](auth.md) | JWT auth, JWKS, route protection, RLS |
| [stack-wiring.md](stack-wiring.md) | Bootstrap, config, middleware, dependency injection |
| [modal-jobs.md](modal-jobs.md) | Modal setup, job lifecycle, API endpoints, orphan recovery |
| [patterns.md](patterns.md) | Service→DAO, adding features, error handling, conventions |

---

## Quick Reference

- **API entry**: `src/api/main.py`
- **Config**: `src/models/config.py` — `load_settings()`
- **Auth**: `src/api/dependencies.py` — `get_current_user`, `get_validated_jwt_user`
- **DB**: `src/config/supabase.py`, `src/config/database.py`
- **Jobs**: `src/services/job_queue/`, `src/deployment/modal_workers.py`
- **Deploy**: `uv run deploy_dev` or `uv run deploy_prod`
