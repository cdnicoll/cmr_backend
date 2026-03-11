---
name: update-runbook
description: Add or update a section in docs/runbook.md. Invoke when a new pipeline phase is complete or existing commands have changed.
disable-model-invocation: true
---

You are the maintainer of `docs/runbook.md` for the CMR backend. Your job is to keep it accurate, lean, and consistent.

## Runbook location

`docs/runbook.md`

## Fixed structure

The runbook has these top-level sections. Do not add new top-level sections or reorder existing ones without explicit instruction:

1. **Setup** — one-time setup commands
2. **JWT** — how to get a JWT token for API testing
3. **Deploy** — how to deploy to Modal and the secret-push pattern
4. **Pillars** — one `###` subsection per pipeline stage (currently: Resources, Scrape: Website, Scrape: YouTube)
5. **Supabase: Common Queries** — SQL for checking resource state

## Pillar section pattern

Read `.claude/skills/update-runbook/section-template.md` for the exact template. Key rules:

- One sentence of context maximum — no explanatory prose
- Commands only — Modal CLI invocations or curl commands
- Single-line prerequisites (not a bullet list)
- **Verify** block: table name, field, expected value
- **Failures** block: only actionable entries — tell the developer exactly what to check or fix; omit generic errors

## Source of truth for commands

Before adding or updating a pillar, always read:
- `specs/NNN-name/quickstart.md` — primary source for commands and verify steps
- `_local/README.md` — for resolved decisions and config that affect the section (env vars, deploy, library choices)

Do not invent commands. Read the source first.

## Rules

- **Do not touch unrelated sections** — when updating one pillar, leave all others unchanged
- **No duplication** — do not repeat what is in `_local/` or `specs/`; the runbook is a command reference, not a knowledge base
- **Failures only if actionable** — if a failure has no specific fix, omit it
- **No version pinning** — do not reference specific library versions in the runbook
- **Horizontal rules between pillars** — maintain the `---` separator between each pillar subsection

## When invoked

1. Read `$ARGUMENTS` to understand what changed (new phase complete, command updated, env var added, etc.)
2. Identify which section needs to change — add a new pillar or update an existing one
3. Read the relevant `specs/NNN-name/quickstart.md` and `_local/README.md`
4. Apply the change using the section template
5. Do not reformat, reorder, or touch anything else
