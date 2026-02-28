-- 002_resources: resources table with pipeline_stage, indexes, updated_at trigger
-- Idempotent: uses IF NOT EXISTS / CREATE OR REPLACE

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    title TEXT,
    type TEXT NOT NULL CHECK (type IN ('website', 'youtube')),
    pipeline_stage TEXT NOT NULL DEFAULT 'discovered' CHECK (pipeline_stage IN ('discovered', 'scraping', 'scraped', 'extracting', 'extracted', 'ingesting', 'complete', 'failed')),
    failure_reason TEXT,
    scraped_content JSONB,
    insight JSONB,
    discovery_source_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS resources_url_key ON public.resources (url);
CREATE INDEX IF NOT EXISTS resources_pipeline_stage_idx ON public.resources (pipeline_stage);
CREATE INDEX IF NOT EXISTS resources_created_at_idx ON public.resources (created_at);

DROP TRIGGER IF EXISTS resources_updated_at ON public.resources;
CREATE TRIGGER resources_updated_at
BEFORE UPDATE ON public.resources
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
