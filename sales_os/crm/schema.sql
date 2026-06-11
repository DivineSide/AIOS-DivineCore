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
