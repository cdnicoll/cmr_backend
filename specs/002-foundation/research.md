# Research: Phase 1 — Foundation (Resources and Auth)

**Feature**: 002-foundation  
**Date**: 2025-02-27 | **Phase**: 0

## Context

Phase 1 adds the Resources domain and confirms Auth. The build plan and domain findings provide clear scope. No unknowns marked as NEEDS CLARIFICATION. This document consolidates decisions for traceability.

---

## 1. URL Validation & SSRF Protection

**Decision**: Implement `url_validation.py` with: (a) SSRF protection — block internal IPs, localhost, private ranges (RFC 1918, etc.); (b) URL normalization — scheme (https preferred), trailing slashes; (c) type detection — `website` vs `youtube`; (d) YouTube-specific format validation.

**Rationale**: Domain findings require SSRF protection and type detection for downstream routing (Crawl4AI website vs YouTube paths). Normalization ensures consistent deduplication on `url`.

**Alternatives considered**:
- External library (e.g. `validators`): May not cover SSRF or YouTube specifics; custom module keeps control.
- Defer SSRF to Phase 2: Security should be in place at intake; Phase 1 is the entry point.

**Implementation notes**: Use `urllib.parse` for parsing; resolve hostname and check against blocked IP ranges. YouTube: validate `youtube.com/watch`, `youtu.be/` patterns.

---

## 2. Auth Model

**Decision**: Use starter kit's Supabase JWT auth as-is. No API key table. All callers (UI, cron, Modal scheduled functions) authenticate via JWT. Programmatic callers use a dedicated service account JWT stored as a Modal secret.

**Rationale**: Build plan explicitly resolved this — JWT-only. Legacy API keys are not migrated. Simpler; single auth path.

**Alternatives considered**:
- Add API key table: Rejected per build plan; JWT + service account suffices.
- Optional auth for batch create: Rejected; resources are user-scoped or system-scoped; JWT required.

---

## 3. Resource Schema & Pipeline Stage

**Decision**: Introduce `pipeline_stage` in Phase 1. Values: `discovered`, `scraping`, `scraped`, `extracting`, `extracted`, `ingesting`, `complete`, `failed`. Drop legacy `scrape` bool and dual status columns (`insight_status`, `graphiti_status`).

**Rationale**: Unified lifecycle simplifies downstream phases. Phase 2+ will transition stages; Phase 1 creates resources in `discovered`.

**Alternatives considered**:
- Minimal schema, add `pipeline_stage` in Phase 2: Rejected; build plan specifies Phase 1 introduction.
- Keep `scrape` flag: Rejected; eligibility derived from `pipeline_stage`.

---

## 4. Duplicate Handling

**Decision**: Unique constraint on `url`. On duplicate: skip insert, return 200 with existing `resource_id` in batch results. Do not error.

**Rationale**: Domain findings and build plan both specify skip semantics. Idempotent for discovery and batch imports.

**Alternatives considered**:
- Error on duplicate: Rejected; batch semantics require per-URL status.
- Upsert: Overkill; we only need to skip.

---

## 5. Batch Response Structure

**Decision**: Response shape: `created`, `skipped`, `errors` (counts); `results` array with per-URL `{ url, status, resource_id?, error? }`.

**Rationale**: Matches legacy `BatchCreateResourceResponse`; clients need per-URL feedback.

---

## 6. Data Access Pattern

**Decision**: Supabase client for `resources` CRUD. Service role for internal operations. ResourcesService → ResourcesDAO per starter-kit patterns.

**Rationale**: Starter uses Supabase for CRUD; asyncpg for jobs/PGMQ. Resources are CRUD-only in Phase 1; Supabase fits.

**Alternatives considered**:
- asyncpg for resources: Possible but starter pattern is Supabase for domain tables; consistency.

---

## 7. Migration Location

**Decision**: Add `resources` table via migration script. Extend `scripts/migrate.py` or add `docs/db/migrations/002_resources.sql` and run from migrate script. Idempotent (`CREATE TABLE IF NOT EXISTS` or equivalent).

**Rationale**: Starter uses `scripts/migrate.py`; extend for new tables. Idempotent per data-layer conventions.

---

## Summary

| Area | Decision | Key Rationale |
|------|----------|---------------|
| URL validation | Custom `url_validation.py` | SSRF, normalize, type detection |
| Auth | JWT only (starter) | No API keys; service account for cron/Modal |
| Resource schema | `pipeline_stage` from Phase 1 | Unified lifecycle |
| Duplicates | Skip, return 200 | Idempotent batch |
| Batch response | created/skipped/errors + results | Per-URL feedback |
| Data access | Supabase, ResourcesService→ResourcesDAO | Starter pattern |
| Migration | Extend migrate.py | Idempotent |
