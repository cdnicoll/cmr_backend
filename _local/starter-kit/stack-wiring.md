# Starter Kit — Stack Wiring

How the app bootstraps, loads config, and connects components.

---

## Bootstrap and Initialization

### Entry Point

**Local dev**: `scripts/dev.py` → `uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)`

**Modal API**: `src/deployment/modal_app.py` → `@asgi_app()` wraps FastAPI app.

### Lifespan

**File**: `src/api/main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: log environment
    yield
    # Shutdown: log shutdown
```

### Middleware Order (outer → inner)

1. **CORS** — `allow_origins=["*"]`, `allow_credentials=True`
2. **Metrics** — `MetricsMiddleware` (timing, error rate, percentiles)
3. **Rate Limiter** — `RateLimiter` (per-user, per-endpoint)
4. **Request ID** — `add_request_id_middleware` (X-Request-ID)

---

## Environment Config

**File**: `src/models/config.py`

- **Loader**: `load_dotenv()` then `Settings()` (pydantic-settings).
- **Config**: `Settings(BaseSettings)` with `validation_alias` for env var names.
- **Validation**: `validate_environment()`, `validate_log_level()`, `validate_transaction_pooler_settings()`.

### Required Variables

| Variable | Purpose |
|----------|---------|
| `ENVIRONMENT` | develop | production |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable key (sb_publishable_...) |
| `SUPABASE_SECRET_KEY` | Secret key (sb_secret_...) |
| `TRANSACTION_POOLER_URL` | DB connection (Shared Pooler) |
| `MODAL_APP_NAME` | Modal API app name |

### Optional

- `LOG_LEVEL`, `API_BASE_URL`, `APOLLO_API_KEY`, `OPENAI_API_KEY`, Azure OpenAI vars, rate limit vars, etc.

---

## Frontend–Backend Communication

- **Protocol**: REST over HTTPS.
- **Auth**: `Authorization: Bearer <jwt>`.
- **Base URL**: From `API_BASE_URL` or Modal deployment URL.
- **CORS**: `allow_origins=["*"]` (tighten for production).

---

## Background Jobs and Async

- **Jobs**: Created via `POST /jobs`, processed by Modal workers.
- **Queue**: PGMQ for backup; primary path is immediate Modal spawn.
- **Recovery**: `recover_orphaned_jobs` runs every 15 minutes (Modal schedule).

---

## External Services

| Service | Integration |
|---------|-------------|
| Supabase | `supabase` client, PostgREST |
| Apollo | `httpx` for company enrichment |
| OpenAI / Azure | Pydantic AI agents, embeddings |
| Modal | `modal.Function.from_name()` for spawning workers |

---

## Dependency Injection

**File**: `src/api/dependencies.py`

Common factories:

- `get_settings()` → `Settings`
- `get_supabase_client()` → Supabase client
- `get_authenticated_supabase_client()` → Client with JWT
- `get_current_user()` → `CurrentUser`
- `get_validated_jwt_user()` → `ValidatedJWTUser`
- `get_*_service()` → Domain services (supplier, company, job queue, etc.)

Services are composed: e.g. `get_supplier_service` depends on `get_supabase_service`.
