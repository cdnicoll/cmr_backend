-- 001_jobs: PGMQ extension, jobs table, job_queue
-- Idempotent: uses IF NOT EXISTS / IF EXISTS

CREATE EXTENSION IF NOT EXISTS pgmq;

CREATE TABLE IF NOT EXISTS public.jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    user_id UUID NOT NULL,
    job_parameters JSONB,
    error_message TEXT,
    error_type TEXT,
    error_context JSONB,
    data_references JSONB,
    retry_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_status_idx ON public.jobs (status);
CREATE INDEX IF NOT EXISTS jobs_user_id_idx ON public.jobs (user_id);
CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON public.jobs (created_at);

-- job_queue: ignore if already exists (duplicate_object, 55000, or "already member")
DO $$
BEGIN
    PERFORM pgmq.create('job_queue');
EXCEPTION
    WHEN duplicate_object THEN NULL;
    WHEN sqlstate '55000' THEN NULL;
    WHEN OTHERS THEN
        IF SQLERRM LIKE '%already%member%' OR SQLERRM LIKE '%already exists%' THEN
            NULL;
        ELSE
            RAISE;
        END IF;
END
$$;
