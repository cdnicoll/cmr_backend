-- 007_resource_scraped_ingested_at: when scrape/ingestion completed successfully
-- scraped_at set when pipeline_stage moves to 'scraped'; ingested_at when 'complete'.

ALTER TABLE public.resources
ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ NULL;

ALTER TABLE public.resources
ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS resources_scraped_at_idx ON public.resources (scraped_at);
CREATE INDEX IF NOT EXISTS resources_ingested_at_idx ON public.resources (ingested_at);
