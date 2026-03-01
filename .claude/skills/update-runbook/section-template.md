# Pillar Section Template

Use this when adding a new pillar section to `docs/runbook.md`.

---

### [Phase Name]: [Short Label]

```bash
[primary command — modal run or curl]
```

[Prerequisites as a single line — e.g. "Resource must have `pipeline_stage = discovered` and `type = website`."]

**Verify**: Supabase `resources` — `pipeline_stage = [expected]`, [key fields and expected values].

**Failures**:
- `[error or state]` — [what to check or fix]
- `[error or state]` — [what to check or fix]

---

## Source guidance

Always read `specs/NNN-name/quickstart.md` for the phase being added. Extract:
- The primary command (Modal CLI invocation or curl)
- The verify steps (pipeline_stage transitions, field values)
- Only failure cases that are actionable — skip generic troubleshooting text

One sentence of context is the maximum. No prose explanations.
