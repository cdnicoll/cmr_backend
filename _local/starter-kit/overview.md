# Starter Kit — Architecture Overview

This document captures the architecture of this application as a blueprint for building a new app with the same stack and approach. It focuses on structure, patterns, and wiring—not business logic.

---

## Tech Stack Inventory

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Framework** | FastAPI | Async HTTP API, OpenAPI docs, dependency injection |
| **Runtime** | Python 3.11+ | Language and runtime |
| **Database** | Supabase (PostgreSQL) | Primary data store, PostgREST, RLS |
| **ORM / Access** | Supabase Client + asyncpg | Supabase for CRUD/RLS; asyncpg for raw SQL, PGMQ, jobs |
| **Auth** | Supabase Auth (JWT) | User identity, JWKS verification |
| **Hosting (API)** | Modal | Serverless API deployment |
| **Hosting (Workers)** | Modal | Background job workers (GPU, browser, LLM, API tiers) |
| **Queue** | PGMQ (Supabase Queues) | Job queue backup and recovery |
| **AI/LLM** | Pydantic AI, OpenAI/Azure | Agents, embeddings, chat |
| **Package Manager** | uv | Dependencies, scripts, virtual env |
| **Validation** | Pydantic, pydantic-settings | Config, request/response models |
| **Secrets** | Infisical + Modal Secrets | Environment-specific secrets |

### Key Libraries

- **fastapi** — API framework
- **uvicorn** — ASGI server
- **supabase** — Supabase Python client
- **modal** — Serverless compute
- **pyjwt**, **cryptography** — JWT verification (JWKS)
- **sqlalchemy**, **asyncpg** — Async DB sessions, transaction pooler
- **pydantic-ai** — AI agent framework
- **httpx** — HTTP client
- **python-dotenv** — `.env` loading

---

## How the Stack Connects

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT (Frontend)                               │
│                    JWT in Authorization: Bearer header                     │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    MODAL (API-{ENVIRONMENT})                              │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  FastAPI App (src.api.main)                                         │ │
│  │  Middleware: CORS → Metrics → Rate Limiter → Request ID              │ │
│  │  Routes: health, items, companies, jobs                             │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────────┐    ┌────────────────────────────┐
│  Supabase    │    │  Transaction      │    │  Modal Workers             │
│  Client      │    │  Pooler           │    │  (Job-Worker-{ENV})         │
│  PostgREST   │    │  asyncpg/SQLAlchemy│   │  GPU / Browser / LLM / API  │
│  RLS         │    │  PGMQ, jobs table  │    │  + recover_orphaned_jobs   │
└──────────────┘    └──────────────────┘    └────────────────────────────┘
         │                    │
         └────────────────────┴──────────────────► Supabase PostgreSQL
```

- **API** receives requests, validates JWT, injects dependencies, calls services.
- **Supabase Client** handles most CRUD via PostgREST; RLS enforces access control.
- **Transaction Pooler** (asyncpg) is used for jobs, PGMQ, and custom SQL.
- **Modal Workers** run background jobs; they are spawned from the API and use the same DB and config.

---

## Notable Architectural Decisions

1. **Dual database access**
   - Supabase Client for CRUD and RLS.
   - asyncpg/SQLAlchemy for jobs, PGMQ, and transactional logic.

2. **JWT verification via JWKS**
   - Uses Supabase JWKS endpoint for asymmetric verification.
   - JWKS client cached for 10 minutes.

3. **Tiered Modal workers**
   - Jobs routed by type to GPU, browser, LLM, or API tiers.
   - Each tier has its own image and resource limits.

4. **Immediate spawn + PGMQ backup**
   - Jobs are spawned to Modal immediately.
   - PGMQ stores messages as backup; recovery worker handles orphans.

5. **Service → DAO pattern**
   - Services (`src/services/`) orchestrate logic.
   - DAOs (`*_dao.py`) encapsulate Supabase/DB access.

6. **Environment-driven deployment**
   - `ENVIRONMENT` (develop/production) controls app names and secrets.
   - Modal secrets named `*-{ENVIRONMENT}`.
