# Starter Kit — Data Layer

How the database is connected, configured, and accessed.

---

## Connection Strategy

Two access paths:

1. **Supabase Client** — PostgREST API, RLS, primary CRUD.
2. **asyncpg / SQLAlchemy** — Raw SQL, PGMQ, jobs table, transaction pooler.

---

## Supabase Client

**File**: `src/config/supabase.py`

**Factory**: `get_supabase_client(use_service_role=False, jwt_token=None)`

| Mode | Key | RLS | Cached |
|------|-----|-----|--------|
| Service role | `SUPABASE_SECRET_KEY` | Bypassed | Yes |
| Publishable (anon) | `SUPABASE_PUBLISHABLE_KEY` | Enforced | Yes |
| Publishable + JWT | Publishable + `jwt_token` | Uses `auth.uid()` | No |

```python
# Service role (internal, bypasses RLS)
client = get_supabase_client(use_service_role=True)

# JWT-authenticated (RLS evaluated per request)
client = get_supabase_client(use_service_role=False, jwt_token=token)
client.postgrest.auth(jwt_token)  # Set for RLS
```

---

## Transaction Pooler (asyncpg / SQLAlchemy)

**File**: `src/config/database.py`

- **URL**: `TRANSACTION_POOLER_URL` (Supabase Shared Pooler, IPv4-compatible).
- **Driver**: `postgresql+asyncpg://` for SQLAlchemy; `postgresql://` for asyncpg.
- **Settings**: Pool size, max overflow, pool recycle, `statement_cache_size=0` (Supabase best practice).

**Session factory**: `get_transaction_session_factory()` → `AsyncSession` for transactional work.

**Health check**: `check_transaction_pooler_health()` — used by `/health/db`.

---

## Data Access Patterns

### Supabase (CRUD)

- **Service**: `SupabaseService` in `src/services/supabase/__init__.py`.
- **DAOs**: `SupplierDAO`, `CompanyDAO`, `AssessmentDAO`, etc. in `src/services/supabase/`.
- **Pattern**: `Service.method()` → `DAO.method()` → `client.table(...).select/insert/update/delete()`.

Example:

```python
result = self.client.table("companies").select("id, name").eq("id", company_id).execute()
```

### asyncpg (Jobs, PGMQ)

- **Pool**: `src/services/job_queue/queue.py` — `get_pool()` returns asyncpg pool.
- **Jobs**: `src/services/job_queue/database.py` — `create_job`, `get_job_by_id`, `update_job_status`, etc.
- **PGMQ**: `queue.send_job_message()`, `queue.read_job_messages()`, `queue.delete_job_message()`.

---

## Migrations

- **Location**: `docs/db/migrations/` (SQL files).
- **Schema docs**: `docs/db/data-model-schema.md`.
- **Functions**: `docs/db/functions/` — one file per DB function.
- **Management**: SQL applied manually or via Supabase migrations; no ORM migrations.

---

## Data Models

- **No SQLAlchemy ORM models** — tables are used via Supabase or raw SQL.
- **Pydantic models** in `src/models/` for validation and serialization.
- **API schemas** in `src/api/schemas/` for request/response shapes.

---

## Conventions

1. **Service role** for internal operations (jobs, profile lookup, recovery).
2. **JWT client** when RLS must apply (user-scoped reads/writes).
3. **Transaction pooler** for jobs, PGMQ, and any multi-statement transactions.
4. **JSONB** for `job_parameters`, `error_context`, `data_references` in `jobs` table.
