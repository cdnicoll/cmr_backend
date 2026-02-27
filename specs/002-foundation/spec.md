# Feature Specification: Phase 1 — Foundation (Resources and Auth)

**Feature Branch**: `002-foundation`  
**Created**: 2025-02-27  
**Status**: Draft  
**Input**: `_local/build-plan.md` Phase 1, `_local/domain_findings/domains/01-resources.md`, `07-authentication.md`

## Summary

Phase 1 establishes the **Resources** domain and confirms **Auth** wiring. Resources is the entry point for all content into the CMR pipeline. Auth uses the starter kit's Supabase JWT as-is; no API key system.

## Clarifications

### From build-plan.md (resolved)

- **Auth model**: Use starter JWT only. No API key table. Cron and scheduled Modal functions authenticate via a dedicated service account JWT stored as a Modal secret.
- **Resource schema**: Introduce `pipeline_stage` from the start. Values: `discovered`, `scraping`, `scraped`, `extracting`, `extracted`, `ingesting`, `complete`, `failed`.
- **Scrape flag**: Drop legacy `scrape` bool. Eligibility derived from `pipeline_stage` — anything in `discovered` is eligible.

## User Scenarios & Testing

### User Story 1 — Create Resources via Batch API (Priority: P1)

As a client (UI, cron, or Modal discovery), I need to submit URLs via `POST /api/v1/resources` so new content sources enter the pipeline for scraping and analysis.

**Independent Test**: `POST /api/v1/resources` with valid URL returns 201; resource appears in Supabase with `pipeline_stage = discovered`.

**Acceptance Scenarios**:

1. **Given** I am authenticated, **When** I `POST /api/v1/resources` with a valid website URL, **Then** I receive 201 and the resource is created with `pipeline_stage = discovered`, `type = website`
2. **Given** I am authenticated, **When** I `POST /api/v1/resources` with a valid YouTube URL, **Then** I receive 201 and the resource is created with `type = youtube`
3. **Given** a resource with the same URL already exists, **When** I submit the same URL again, **Then** I receive 200 (skipped) and no duplicate is created
4. **Given** I submit an invalid or SSRF URL, **When** the request is processed, **Then** I receive 422 with validation error
5. **Given** I submit a batch of URLs (some valid, some invalid, some duplicates), **When** the request is processed, **Then** I receive a response with `created`, `skipped`, `errors` and per-URL results

---

### User Story 2 — Auth Protection (Priority: P1)

As the system, protected endpoints must require a valid JWT so only authenticated callers can create or access resources.

**Independent Test**: Hit `POST /api/v1/resources` without a JWT — confirm 401.

**Acceptance Scenarios**:

1. **Given** no JWT is provided, **When** I call `POST /api/v1/resources`, **Then** I receive 401
2. **Given** an invalid or expired JWT, **When** I call a protected endpoint, **Then** I receive 401 with `WWW-Authenticate: Bearer`

---

### User Story 3 — Bootstrap Resource Schema (Priority: P1)

As a developer, I need to run a migration to create the `resources` table so the Resources API can function.

**Independent Test**: Run migration script; verify `resources` table exists with expected columns including `pipeline_stage`, `failure_reason`.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** I run the migration script, **Then** the `resources` table exists with `url` (unique), `pipeline_stage`, `type`, `failure_reason`, `scraped_content`, `insight`, `discovery_source_id`, etc.
2. **Given** schema already exists, **When** I run the migration again, **Then** it completes without error (idempotent)

## Edge Cases

- Duplicate URL → skip, return 200 with existing resource_id in results; do not error
- SSRF URL (internal IP, localhost, private range) → 422
- Malformed URL → 422
- YouTube URL format validation → per domain findings
- Batch: individual URL errors do not fail the batch; each result has status `created` | `skipped` | `error`

## Requirements

### Functional Requirements

- **FR-001**: System MUST expose `POST /api/v1/resources` accepting an array of URLs; validates each, inserts new resources, skips duplicates
- **FR-002**: URL validation MUST include SSRF protection (block internal IPs, localhost, private ranges)
- **FR-003**: URL validation MUST normalize scheme and trailing slashes; detect type (`website` | `youtube`)
- **FR-004**: Duplicate URLs MUST be skipped (unique on `url`); response indicates skipped with existing resource_id
- **FR-005**: Resources table MUST include `pipeline_stage` with values: `discovered`, `scraping`, `scraped`, `extracting`, `extracted`, `ingesting`, `complete`, `failed`
- **FR-006**: Resources table MUST include `failure_reason` (TEXT, nullable) for failed resources
- **FR-007**: Auth MUST use starter JWT (`get_validated_jwt_user` or `get_current_user`); no API key system
- **FR-008**: Protected routes MUST return 401 when JWT is missing or invalid
- **FR-009**: Migration script MUST create `resources` table idempotently

### Key Entities

- **Resource**: `id`, `url` (unique), `title`, `type` (`website`|`youtube`), `pipeline_stage`, `failure_reason`, `scraped_content`, `insight`, `discovery_source_id`, `created_at`, `updated_at`

## Success Criteria

- **SC-001**: `POST /api/v1/resources` with valid URL returns 201; resource in Supabase with `pipeline_stage = discovered`
- **SC-002**: Duplicate URL returns 200 (skipped)
- **SC-003**: Invalid/SSRF URL returns 422
- **SC-004**: YouTube URL detected as `type = youtube`
- **SC-005**: Protected endpoint without JWT returns 401
- **SC-006**: Migration creates `resources` table; idempotent
