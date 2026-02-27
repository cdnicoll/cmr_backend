# Domain: Authentication

## Purpose

The Authentication domain secures API access via **API key validation**. Keys are stored in PostgreSQL, validated on each request, and support optional scopes for fine-grained authorization.

## Core Behavior

1. **API key validation** (`validate_api_key` dependency):
   - Extracts Bearer token from `Authorization` header
   - Looks up key in `api_keys` table
   - Checks: exists, active, not expired
   - Updates `last_used_at`
   - Returns key metadata (key_id, scopes, rate limits)

2. **Optional auth** (`optional_api_key`):
   - Same validation, but missing/invalid key returns unauthenticated state instead of 401
   - Used for health checks, root endpoint

3. **Scope enforcement** (`require_scopes`):
   - Factory that creates dependency requiring specific scopes (e.g. `["admin"]`)
   - 403 if key lacks required scopes

## Key Data

- **api_keys table**: key hash, scopes, rate_limit_per_minute, rate_limit_per_hour, expires_at, last_used_at
- **Validation result**: is_valid, key_id, scopes, error_message

## Boundaries

- **Depends on**: PostgreSQL (api_keys), APIKeyService
- **Depended on by**: All protected API routes

## Edge Cases and Notable Logic

- **401 vs 403**: Invalid key → 401; Valid but inactive/expired → 403
- **Rate limiting**: Configured per-key but SlowAPI uses `get_remote_address` by default — key-based limits may not be fully applied
- **Bearer scheme**: `HTTPBearer(auto_error=False)` — no key doesn't auto-raise for optional endpoints

## What to Preserve

- Bearer token extraction and validation flow
- Optional vs required auth distinction
- Scope-based authorization pattern
