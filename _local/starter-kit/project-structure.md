# Starter Kit — Project Structure

A commented directory tree and guide to where key pieces live.

---

## Directory Tree

```
app/
├── src/                          # Main application source
│   ├── api/                      # FastAPI application
│   │   ├── main.py               # App entry, lifespan, middleware, route registration
│   │   ├── dependencies.py       # FastAPI Depends() factories (auth, services, config)
│   │   ├── routes/               # Route modules
│   │   │   ├── health.py         # /health, /health/db
│   │   │   ├── companies.py      # Company endpoints
│   │   │   ├── items.py          # Item/resource endpoints
│   │   │   ├── jobs/
│   │   │   │   └── router.py     # POST/GET /jobs
│   │   │   └── items/            # Nested router
│   │   │       ├── __init__.py   # Aggregates sub-routers
│   │   │       ├── crud.py       # Item CRUD
│   │   │       ├── imports.py    # CSV import
│   │   │       └── chat.py
│   │   └── schemas/              # Request/response Pydantic models (API-specific)
│   │
│   ├── config/                   # Connection and client factories
│   │   ├── supabase.py           # get_supabase_client() — cached clients
│   │   └── database.py           # Transaction pooler, AsyncSession, engine
│   │
│   ├── deployment/                # Modal deployment
│   │   ├── modal_app.py          # API app (ASGI wrapper)
│   │   ├── modal_workers.py      # Worker functions (GPU, browser, LLM, API, recovery)
│   │   ├── deploy.py             # Deploy script (Infisical → secrets → deploy)
│   │   └── create_modal_secrets.sh
│   │
│   ├── middleware/               # HTTP middleware
│   │   ├── __init__.py
│   │   └── metrics.py            # Request timing, error rate, percentiles
│   │
│   ├── models/                   # Pydantic models (domain + config)
│   │   ├── config.py             # Settings (pydantic-settings), load_settings()
│   │   ├── common.py             # ErrorResponse, etc.
│   │   ├── responses.py          # CurrentUser, ValidatedJWTUser, API responses
│   │   └── jobs/                 # Job-related models
│   │       ├── job.py            # JobCreateRequest, JobResponse, etc.
│   │       └── job_status.py     # JobStatus, JobType enums
│   │
│   ├── services/                 # Business logic layer
│   │   ├── supabase/             # Supabase data access
│   │   │   ├── __init__.py       # SupabaseService, DAO wiring
│   │   │   ├── base.py           # BaseDAO
│   │   │   ├── item_dao.py
│   │   │   ├── company_dao.py
│   │   │   └── ...               # Other *_dao.py
│   │   ├── job_queue/            # Job queue orchestration
│   │   │   ├── service.py        # JobQueueService (create, process, list)
│   │   │   ├── spawner.py        # spawn_job() — routes to Modal
│   │   │   ├── database.py       # jobs table CRUD, stuck/orphan detection
│   │   │   └── queue.py          # PGMQ send/read/delete
│   │   ├── database/             # Transaction session, pool management
│   │   └── ...                   # Domain services (item, company, etc.)
│   │
│   ├── agents/                    # Pydantic AI agents
│   │   └── {agent_name}/
│   │       ├── agent.py
│   │       ├── tools.py
│   │       ├── models.py
│   │       └── dependencies.py
│   │
│   ├── integrations/             # External API integrations
│   ├── utils/                    # Logging, rate limiter, validation
│   └── cli/                      # CLI command modules
│
├── tests/                        # Unit, integration, contract tests
├── docs/                         # Documentation
├── specs/                        # Feature specs
├── scripts/                      # dev.py, check_database_connections.py
├── data/                         # Static data (templates, fixtures)
│
├── pyproject.toml                # Dependencies, scripts (deploy, secrets)
├── .env.example                  # Environment variable template
└── .env                          # Local config (gitignored)
```

---

## Purpose of Major Folders

| Folder | Purpose |
|--------|---------|
| `src/api/` | FastAPI app, routes, dependencies, schemas |
| `src/config/` | Supabase client factory, DB engine, transaction pooler |
| `src/deployment/` | Modal app and worker definitions, deploy script |
| `src/middleware/` | Metrics, rate limiting (rate limiter in `utils/`) |
| `src/models/` | Pydantic models for config, responses, jobs |
| `src/services/` | Business logic; services use DAOs for data access |
| `src/agents/` | Pydantic AI agents (tools, models, dependencies) |
| `src/utils/` | Logging, rate limiter, validation helpers |
| `src/cli/` | CLI entry points (crawler, chat, etc.) |

---

## Naming Conventions

- **Routes**: `router = APIRouter(tags=["..."])`; route modules use `router` as export.
- **Services**: `*Service` classes; injected via `get_*_service()` in dependencies.
- **DAOs**: `*DAO` classes; live in `src/services/supabase/*_dao.py`.
- **Models**: Pydantic models in `src/models/`; API schemas in `src/api/schemas/`.
- **Job types**: `JobType` enum in `src/models/jobs/job_status.py`; add new values there.

---

## Where to Find Key Things

| Thing | Location |
|-------|----------|
| **Routes** | `src/api/routes/` — flat or nested routers |
| **API entry** | `src/api/main.py` |
| **Auth** | `src/api/dependencies.py` — `get_current_user`, `get_validated_jwt_user` |
| **Config** | `src/models/config.py` — `Settings`, `load_settings()` |
| **DB connection** | `src/config/supabase.py`, `src/config/database.py` |
| **Job creation** | `src/api/routes/jobs/router.py` → `JobQueueService.create_job()` |
| **Job processing** | `src/services/job_queue/service.py` — `process_job()` |
| **Modal workers** | `src/deployment/modal_workers.py` |
| **Modal API** | `src/deployment/modal_app.py` |
| **Middleware** | `src/middleware/`, `src/utils/rate_limiter.py` |

---

## Route Registration Pattern

Routes are registered in `src/api/main.py`:

```python
from src.api.routes import health, items, companies, jobs

app.include_router(health.router)
app.include_router(items.router)
app.include_router(companies.router)
app.include_router(jobs.router)
```

Nested routers (e.g. items) aggregate in `__init__.py`:

```python
# src/api/routes/items/__init__.py
router = APIRouter(tags=["items"])
router.include_router(crud.router)
router.include_router(imports.router)
router.include_router(chat.router)
```
