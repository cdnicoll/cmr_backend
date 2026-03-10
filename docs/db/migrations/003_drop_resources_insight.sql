-- 003_drop_resources_insight: remove unused insight column (extraction superseded by Graphiti)
ALTER TABLE public.resources DROP COLUMN IF EXISTS insight;
