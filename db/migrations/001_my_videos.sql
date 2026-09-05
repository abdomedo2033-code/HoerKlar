-- Phase 5 — My videos + ingest jobs (Supabase/Postgres).
-- Auto-ingested rows are ALWAYS unverified + personal. Promotion to shared
-- sections (movies/series/songs) is a human UPDATE, never automatic.

create table if not exists ingest_jobs(
  id uuid primary key default gen_random_uuid(),
  user_id text not null default 'local',
  youtube_id text not null,
  url text not null,
  status text not null default 'queued'
    check(status in ('queued','fetching_subs','aligning','transcribing',
                     'distractors','translating','done','error')),
  progress float default 0,
  error text,
  created_at timestamptz default now()
);
create index if not exists ingest_jobs_user_day
  on ingest_jobs(user_id, created_at);

-- Personal section: one row per user video; clips reference it.
alter table videos add column if not exists owner_user text;
alter table videos add column if not exists section text default 'movies';

-- Personal clips stay approved=false + rights EMBED_ONLY/UNKNOWN until review.
-- Promotion checklist (human glance before sharing):
--   1. transcript matches audio for 2-3 sampled clips
--   2. translations read naturally (no semantic drift)
--   3. rights_status re-checked (Standard YouTube licence => stays personal-only)
--   update clips set approved=true where video_id in (...);
