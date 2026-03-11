<!--
Sync Impact Report
==================
Version change: (none) → 1.0.0
Modified principles: N/A (initial creation)
Added sections: All (initial constitution)
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ (Constitution Check gate aligns)
  - .specify/templates/spec-template.md ✅ (no mandatory section changes)
  - .specify/templates/tasks-template.md ✅ (observability/logging task types supported)
  - .cursor/commands/*.md ✅ (no agent-specific references to update)
Follow-up TODOs: None
-->

# CMR Backend Constitution

## Core Principles

### I. Quick Start (10-Minute Rule)

A new developer MUST be able to clone the repository, follow setup steps, and have
the application running locally in under 10 minutes. The project MUST provide:

- A single-source setup guide (e.g., README or docs/quickstart.md)
- Minimal prerequisites with clear installation instructions
- One-command or few-command run path (e.g., `uv run` or equivalent)
- No hidden or undocumented steps that block first run

**Rationale**: Fast onboarding reduces friction and enables developers to contribute
quickly. A 10-minute target is measurable and forces simplification of setup.

### II. REST API Foundation

The application MUST expose a REST API with:

- A health check endpoint (e.g., `GET /health`) returning 200 when the app is up
- Automatic API documentation (OpenAPI/Swagger) available at a documented path
  (e.g., `/docs` or `/openapi.json`)
- Structured request/response models with validation

**Rationale**: Health checks enable deployment probes and monitoring. Automatic docs
reduce maintenance burden and ensure API contracts stay discoverable.

### III. Cloud-Ready & Scalable

The application MUST be deployable to a cloud platform and scale with traffic. This
implies:

- Stateless design where possible; session state externalized if needed
- Support for horizontal scaling (multiple instances behind a load balancer)
- Environment-driven configuration (no hardcoded deployment targets)
- Deployment instructions or scripts for at least one cloud platform

**Rationale**: Cloud deployment and scalability are non-negotiable for production
readiness. Stateless design simplifies scaling and failure recovery.

### IV. Observability & Request Tracing

Structured logging with request tracing MUST be included so issues can be debugged.
Specifically:

- Every HTTP request MUST receive a unique trace/request ID (e.g., `X-Request-ID`)
- Logs MUST be structured (JSON or key-value pairs) and include the request ID
  when available
- Error responses MUST include the request ID for correlation
- Logging configuration MUST be controllable via environment or config

**Rationale**: Request tracing enables correlating logs across services and
debugging production issues. Structured logs support log aggregation and querying.

### V. Developer Guidance

Project rules and patterns MUST be provided so developers get consistent guidance
when writing code. This includes:

- Documented patterns (e.g., Service→DAO, error handling, validation)
- Cursor rules (`.cursor/rules/` or equivalent) or coding standards
- Conventions for adding features, routes, services, and jobs
- A single reference (e.g., `patterns.md` or `docs/conventions.md`) that agents
  and developers can follow

**Rationale**: Consistent guidance reduces cognitive load and ensures code quality
across contributors. Rules enable AI assistants to produce aligned output.

## Additional Constraints

- **Technology stack**: Align with existing starter kit (FastAPI, Python 3.11+,
  Supabase, Modal) unless explicitly overridden by feature specs.
- **Deployment**: Support at least one cloud deployment path (e.g., Modal) with
  environment-specific configuration.
- **Security**: Secrets MUST NOT be committed; use environment variables or a
  secrets manager (e.g., Infisical, Modal Secrets).

## Development Workflow

- **Constitution Check**: All implementation plans MUST pass a Constitution Check
  gate before Phase 0 research. Re-check after Phase 1 design.
- **Quickstart validation**: New features MUST NOT break the 10-minute setup path;
  run quickstart validation when adding dependencies or setup steps.
- **Rules compliance**: PRs and reviews MUST verify alignment with documented
  patterns and project rules.

## Governance

- This constitution supersedes ad-hoc practices. When in conflict, the constitution
  prevails.
- Amendments require: documented rationale, version bump per semantic versioning,
  and propagation to dependent templates (plan, spec, tasks).
- All PRs and reviews MUST verify compliance with these principles. Complexity
  that violates principles MUST be justified in the plan's Complexity Tracking
  table.
- Use `.cursor/rules/`, `_local/README.md`, and `docs/` for runtime development
  guidance.

**Version**: 1.0.0 | **Ratified**: 2025-02-26 | **Last Amended**: 2025-02-26
