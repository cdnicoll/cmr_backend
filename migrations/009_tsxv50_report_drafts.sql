-- Report draft store for the multi-agent TSXV50 pipeline (issue #1, #12).
-- One row per draft; category jsonb keeps research separate from drafted
-- content so the synthesist can read every category's research before any
-- category-drafter starts. draft_slug supports trying multiple editorial
-- versions of the same period (default 'primary' for the common case); only
-- one row per period_label may be status = 'published' at a time.

create table public.tsxv50_report_drafts (
    id                bigserial    primary key,
    period_label      text         not null,
    draft_slug        text         not null default 'primary',
    status            text         not null default 'in_progress',
    meta              jsonb,
    master_list       jsonb,
    introduction      jsonb,
    categories        jsonb        not null default '{}',
    synthesis         jsonb,
    finalize_result   jsonb,
    conversation_ids  jsonb        not null default '[]',
    pdf_url           text,
    created_at        timestamptz  not null default now(),
    updated_at        timestamptz  not null default now(),

    constraint tsxv50_report_drafts_period_slug_key unique (period_label, draft_slug),
    constraint tsxv50_report_drafts_status_check check (
        status in ('in_progress', 'finalized', 'rendered', 'published', 'archived')
    )
);

-- Only one draft per period may be published at a time.
create unique index tsxv50_report_drafts_one_published_per_period
    on public.tsxv50_report_drafts (period_label)
    where status = 'published';

-- Matches every other public table in this project: locked down to the
-- service role (the DAO/MCP tools connect via the service role and bypass
-- RLS by design); no anon/authenticated policies, same as tsxv50_snapshots.
alter table public.tsxv50_report_drafts enable row level security;
