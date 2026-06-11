-- Cold Call Dialer tables. SEPARATE from crm_*. Run once in Supabase Studio.
-- Writes go through PostgREST with the server-side secret key, so default RLS is fine.

-- ---------------------------------------------------------------------------
-- call_prospects: one row per lead to dial.
-- ---------------------------------------------------------------------------
create table if not exists call_prospects (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  business_name     text default '',
  phone             text default '',          -- E.164, e.g. +14155550123
  raw_phone         text default '',          -- as it arrived in the CSV
  area_code         text default '',
  time_zone         text default '',          -- IANA, e.g. America/Los_Angeles
  calling_block     text default '',          -- morning | night | '' (unknown)
  email             text default '',
  website           text default '',
  city              text default '',
  state             text default '',
  status            text default 'new',       -- see ENUM note below
  next_follow_up_at timestamptz,
  source            text default 'csv',
  needs_review      boolean default false,    -- phone unparseable / no US time zone
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);

-- Dedupe on phone (only for rows that actually have one).
create unique index if not exists call_prospects_phone_uidx
  on call_prospects (phone) where phone <> '';
create index if not exists call_prospects_block_idx    on call_prospects (calling_block);
create index if not exists call_prospects_status_idx   on call_prospects (status);
create index if not exists call_prospects_followup_idx on call_prospects (next_follow_up_at);

-- ---------------------------------------------------------------------------
-- call_logs: one row per call attempt. Many per prospect.
-- ---------------------------------------------------------------------------
create table if not exists call_logs (
  id            uuid primary key default gen_random_uuid(),
  prospect_id   uuid references call_prospects(id) on delete cascade,
  attempted_at  timestamptz default now(),
  disposition   text default '',
  note          text default '',
  created_at    timestamptz default now()
);
create index if not exists call_logs_prospect_idx on call_logs (prospect_id, attempted_at desc);

-- ENUMS (kept as text, validated in the app layer):
--   status / disposition: new, dialed, no_answer, voicemail, not_interested,
--                         callback, booked, wrong_number, do_not_call
