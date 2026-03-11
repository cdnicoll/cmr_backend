-- 005_discovery_first_run_at: first-run vs ongoing discovery
-- NULL = never completed a real run; set after first non-dry_run run that includes this source.

ALTER TABLE public.discovery_sources
ADD COLUMN IF NOT EXISTS first_run_at TIMESTAMPTZ NULL;
