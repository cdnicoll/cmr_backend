-- 004_discovery_sources: discovery_sources table for Phase 5 content discovery
-- Idempotent: uses IF NOT EXISTS; resources.discovery_source_id already exists (002)

CREATE TABLE IF NOT EXISTS public.discovery_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type TEXT NOT NULL CHECK (source_type IN ('sitemap', 'rss', 'youtube_channel')),
    name TEXT,
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS discovery_sources_enabled_idx ON public.discovery_sources (enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS discovery_sources_source_type_idx ON public.discovery_sources (source_type);

DROP TRIGGER IF EXISTS discovery_sources_updated_at ON public.discovery_sources;
CREATE TRIGGER discovery_sources_updated_at
BEFORE UPDATE ON public.discovery_sources
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Optional FK: link resources to their discovery source (referenced in 002)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'resources_discovery_source_id_fkey'
  ) THEN
    ALTER TABLE public.resources
    ADD CONSTRAINT resources_discovery_source_id_fkey
    FOREIGN KEY (discovery_source_id) REFERENCES public.discovery_sources(id);
  END IF;
END $$;
