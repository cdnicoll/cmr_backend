# Starter Kit — Patterns and Conventions

Reusable patterns and how to add new features.

---

## Service → DAO Pattern

**Structure**:

- **Service** (`src/services/`): Orchestrates logic, validates, calls DAOs.
- **DAO** (`src/services/supabase/*_dao.py`): Encapsulates Supabase/DB access.

**Example**:

```python
# Service
class SupplierService:
    def __init__(self, supabase_service: SupabaseService):
        self.supplier_dao = supabase_service.supplier_dao

    async def get_suppliers(self, company_id: str, ...):
        return await self.supplier_dao.get_suppliers(company_id, ...)

# DAO
class SupplierDAO(BaseDAO):
    async def get_suppliers(self, company_id: str, ...):
        result = self.client.table("suppliers").select(...).eq("company_id", company_id).execute()
        return result.data
```

---

## Adding a New Feature

### 1. New Route

1. Create `src/api/routes/{domain}/` or add to existing router.
2. Define `router = APIRouter(tags=["..."])` and endpoints.
3. Use `Depends(get_current_user)` for protected routes.
4. Register in `src/api/main.py` or parent `__init__.py`.

### 2. New Service

1. Create `src/services/{domain}_service.py` or add to existing service.
2. Add `get_{service}_service()` in `src/api/dependencies.py`.
3. Inject via `Depends(get_{service}_service)` in routes.

### 3. New DAO

1. Create `src/services/supabase/{entity}_dao.py` extending `BaseDAO`.
2. Add to `SupabaseService.__init__` and wire in `get_supabase_service`.

### 4. New Job Type

See `modal-jobs.md` — add to `JobType`, `JOB_TIER_MAPPING`, `validate_job_parameters`, `extract_entity_reference`, `process_job`, and `check_duplicate_job`.

---

## Error Handling

**Global handler**: `src/api/main.py` — catches unhandled exceptions, returns `ErrorResponse`.

**Standard format**:

```python
ErrorResponse(
    error="internal_error",
    message="An internal error occurred. Please try again later.",
    request_id=request_id,
)
```

**Route-level**: Use `HTTPException(status_code=..., detail=...)` for expected errors (400, 404, etc.).

---

## Logging

**Setup**: `src/utils/logging.py` — `get_logger(__name__)`, `setup_logging(settings)`.

**Convention**: Include `request_id` in log messages when available.

```python
logger.info(f"Job created (job_id={job_id}, request_id={request_id})")
```

---

## Request ID

- Set by `add_request_id_middleware` in `main.py`.
- Available via `get_request_id(request)` or `request.state.request_id`.
- Returned in `X-Request-ID` response header.
- Use for tracing across logs and error responses.

---

## Rate Limiting

**File**: `src/utils/rate_limiter.py`

- Sliding window per user, per endpoint.
- Endpoint limits in `endpoint_limits` dict.
- Concurrent limit for import endpoint.
- Returns 429 when exceeded.

---

## Validation

- **Request**: Pydantic models as route parameters.
- **Response**: `response_model=...` on route decorator.
- **Config**: `Settings` with `Field()`, `validation_alias`, custom validators.

---

## Code Style Conventions

1. **Async**: Use `async def` for I/O-bound handlers and services.
2. **Type hints**: Use `Annotated[X, Depends(...)]` for injected params.
3. **Imports**: Prefer `from src.` for internal modules.
4. **File length**: Split modules when approaching ~500 lines.
5. **Docstrings**: Use for public functions and classes.

---

## Abstractions Worth Reusing

| Abstraction | Location | Purpose |
|-------------|----------|---------|
| `load_settings()` | `src/models/config.py` | Single config load with validation |
| `get_supabase_client()` | `src/config/supabase.py` | Cached client factory |
| `get_current_user` | `src/api/dependencies.py` | Auth + profile lookup |
| `get_request_id()` | `src/api/dependencies.py` | Request tracing |
| `ErrorResponse` | `src/models/responses.py` | Standard error shape |
| `TransactionContext` | `src/services/database/` | Transaction boundaries |
