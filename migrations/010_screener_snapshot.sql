-- Screener snapshot lock (known gap 13, Billy's reproducibility finding 2026-08-28).
-- The master list and the per-company profile tables were populated from separate
-- screen_tsxv50 pulls taken minutes apart, so a company's market cap in the table
-- disagreed with its own profile by live movement. One pull, stored once, read by
-- every later phase, makes them structurally unable to disagree.
--
-- Nullable and additive: existing rows keep working. The orchestrator writes it once,
-- right after its single screen_tsxv50 call in Phase 1; researchers and the drafter
-- read market data from it instead of re-pulling.

alter table public.tsxv50_report_drafts
    add column if not exists screener_snapshot jsonb;

comment on column public.tsxv50_report_drafts.screener_snapshot is
    'The run''s single screen_tsxv50 result, keyed by symbol. Written once by set_screener_snapshot in Phase 1; the source for every market-data field downstream. meta.data_as_of is this pull''s date.';
