-- LinkedIn engage-first pipeline. Run once in Supabase Studio. Separate table.

create table if not exists li_prospects (
  id               uuid primary key default gen_random_uuid(),
  name             text not null,
  linkedin_url     text default '',
  tier             text default 'A',          -- A | B | C
  stage            text default 'commented',  -- commented|connect_sent|accepted|first_msg|loom_sent|engaged|in_convo|won|dead
  replied          boolean default false,
  next_action_date date,                       -- when the current stage's action is due
  notes            text default '',
  source           text default 'manual',
  created_at       timestamptz default now(),
  updated_at       timestamptz default now()
);

create unique index if not exists li_prospects_url_uidx on li_prospects (linkedin_url) where linkedin_url <> '';
create index if not exists li_prospects_next_idx  on li_prospects (next_action_date);
create index if not exists li_prospects_stage_idx on li_prospects (stage);
