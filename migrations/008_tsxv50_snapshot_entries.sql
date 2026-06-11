-- Add entries jsonb column ({symbol, name, category} objects) for TSXV50 snapshots.
-- Additive, no backfill: existing rows keep their legacy `symbols` array; new rows
-- populate `entries` and leave `symbols` null.

alter table public.tsxv50_snapshots
    alter column symbols drop not null;

alter table public.tsxv50_snapshots
    add column if not exists entries jsonb null;
