-- 006_drop_jobs: Remove legacy job queue (jobs table and PGMQ).
-- Run after 001_jobs if the DB was created with the starter job queue.
-- CMR uses only the resource pipeline (discovery, scrape, ingest); no POST /jobs.

DROP TABLE IF EXISTS public.jobs;

-- Drop PGMQ queue (pgmq.drop_queue returns false if queue does not exist in newer PGMQ)
DO $$
BEGIN
  PERFORM pgmq.drop_queue('job_queue');
EXCEPTION
  WHEN undefined_function THEN
    NULL;  -- extension not installed
  WHEN OTHERS THEN
    IF SQLERRM LIKE '%does not exist%' OR SQLERRM LIKE '%not exist%' THEN
      NULL;
    ELSE
      RAISE;
    END IF;
END
$$;

DROP EXTENSION IF EXISTS pgmq;
