# Starter Kit — Authentication

How authentication is implemented end to end.

---

## Overview

- **Provider**: Supabase Auth.
- **Token**: JWT in `Authorization: Bearer <token>`.
- **Verification**: JWKS (asymmetric) from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`.

---

## Implementation

**File**: `src/api/dependencies.py`

### Token Extraction

```python
security = HTTPBearer()  # Extracts Bearer token from Authorization header
```

### Two Auth Dependencies

| Dependency | Returns | DB Lookup | Use Case |
|------------|---------|-----------|----------|
| `get_current_user` | `CurrentUser` (user_id, company_id) | Yes — profiles table | Routes needing company context |
| `get_validated_jwt_user` | `ValidatedJWTUser` (user_id only) | No | Routes needing only user identity |

### get_current_user Flow

1. Extract token via `Security(security)`.
2. Fetch signing key from JWKS (cached 10 min).
3. Decode JWT with `jwt.decode(..., algorithms=["RS256", "ES256"], audience="authenticated")`.
4. Read `sub` as `user_id`.
5. Query `profiles` with service role client: `select id, company_id where id = user_id`.
6. Return `CurrentUser(user_id=..., company_id=...)`.

### get_validated_jwt_user Flow

1. Same token extraction and JWKS verification.
2. Decode JWT, read `sub`.
3. Return `ValidatedJWTUser(user_id=...)` — no DB call.

---

## Route Protection

Protected routes use `Depends(get_current_user)` or `Depends(get_validated_jwt_user)`:

```python
@router.post("/jobs")
async def create_job(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    job_request: JobCreateRequest,
    ...
) -> JobResponse:
    # current_user.user_id, current_user.company_id available
```

---

## JWKS Caching

- **Client**: `PyJWKClient` from `jwt` library.
- **Cache TTL**: 600 seconds (10 minutes).
- **URL**: `{settings.supabase_url}/auth/v1/.well-known/jwks.json`.

---

## RLS (Row Level Security)

- Supabase RLS policies use `auth.uid()`.
- For RLS to apply, use a client with JWT: `get_supabase_client(jwt_token=token)`.
- Service role client bypasses RLS.

---

## Error Handling

- **401**: Invalid/expired token, wrong audience, decode failure.
- **404**: Profile not found for `get_current_user`.
- **500**: Profile lookup error.

All raise `HTTPException` with `WWW-Authenticate: Bearer` on 401.
