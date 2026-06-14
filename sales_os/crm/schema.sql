-- CRM + KPI tables for the positive-reply pipeline dashboard (served at /crm).
-- Run once in Supabase Studio -> SQL editor. Writes go through PostgREST using
-- the service/secret key (server-side only), so default RLS is fine.

-- ---------------------------------------------------------------------------
-- crm_prospects: one row per lead moving through the positive-reply cadence.
-- ---------------------------------------------------------------------------
create table if not exists crm_prospects (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  company         text default '',
  source          text default 'cold_email',  -- cold_email | linkedin | referral | other
  temp            text default 'warm',         -- hot | warm
  stage           text default 'new',          -- new | contacted | call_booked | showed | won | lost
  email           text default '',
  phone           text default '',
  linkedin_url    text default '',
  next_touch_date date,
  last_touch_at   timestamptz,
  touch_count     int  default 0,
  notes           text default '',
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

create index if not exists crm_prospects_next_touch_idx on crm_prospects (next_touch_date);
create index if not exists crm_prospects_stage_idx      on crm_prospects (stage);

-- ---------------------------------------------------------------------------
-- kpi_daily: one row per (day, metric). The dashboard increments these; the
-- history is what makes long-term tracking possible.
-- ---------------------------------------------------------------------------
create table if not exists kpi_daily (
  id          uuid primary key default gen_random_uuid(),
  date        date not null,
  metric      text not null,
  value       int  default 0,
  updated_at  timestamptz default now(),
  unique (date, metric)
);

create index if not exists kpi_daily_date_idx on kpi_daily (date);

-- ---------------------------------------------------------------------------
-- content_posts: one row per published LinkedIn/X post. Mirrors the manual
-- tracker CSV (tools/social-tracker/posts.csv) so the /crm "Content" dashboard
-- can render the reach-first view (this-week plan, mix, top posts/hooks).
-- Synced up from the CSV via POST /crm/api/content/import (impressions are
-- author-only analytics, can't be scraped, so they're entered by hand first).
-- ---------------------------------------------------------------------------
create table if not exists content_posts (
  post_id        text primary key,            -- stable id from the CSV (e.g. li-... / linkedin-YYYYMMDD-n)
  platform       text not null default 'linkedin',   -- linkedin | x
  posted_at      date,
  url            text default '',
  post_type      text default '',             -- authority | educational | personal | social-proof
  framework      text default '',             -- PAS | SLA | case-study | BAB
  funnel_stage   text default '',             -- top | middle | bottom
  topic          text default '',
  format         text default '',             -- list | story | insight | question | case-study | hot-take | tutorial | announcement | other
  differentiator text default '',
  hook           text default '',
  closing        text default '',
  content        text default '',
  views          int,                         -- impressions (the metric we optimize)
  likes          int,
  comments       int,
  reposts        int,
  bookmarks      int,
  notes          text default '',
  updated_at     timestamptz default now()
);

create index if not exists content_posts_posted_idx   on content_posts (posted_at desc nulls last);
create index if not exists content_posts_platform_idx on content_posts (platform);
create index if not exists content_posts_type_idx     on content_posts (post_type);
