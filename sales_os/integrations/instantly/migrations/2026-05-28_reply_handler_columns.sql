-- Adds reply-handler columns to outreach_replies for the LLM classifier +
-- Gmail draft + follow-up reminder flow. Apply once in Supabase SQL editor.
--
-- After this migration the per-reply lifecycle is:
--   1. Instantly webhook fires -> row inserted with stage='NEW_REPLY',
--      intent/confidence/key_message filled by Claude classifier, Gmail draft
--      created (gmail_thread_id + gmail_draft_id + recommended_reply set).
--   2. Pang sends the draft from Gmail. Stage stays NEW_REPLY (we do not
--      auto-promote at low volume).
--   3. Daily 00:00 UTC beat scans replies where is_positive=true AND
--      stage='NEW_REPLY' AND follow_up_count<3 AND >=24h since last action.
--      For each match, posts a Discord reminder ping and increments
--      follow_up_count + last_follow_up_at. After 3 pings the lead falls
--      out of the scan window naturally.
--
-- Idempotent: every ADD/CREATE uses IF NOT EXISTS, safe to re-run if it
-- only partially applied.

alter table public.outreach_replies
  add column if not exists intent              text,
  add column if not exists confidence          numeric,
  add column if not exists key_message         text,
  add column if not exists stage               text        not null default 'NEW_REPLY',
  add column if not exists gmail_thread_id     text,
  add column if not exists gmail_draft_id      text,
  add column if not exists recommended_reply   text,
  add column if not exists follow_up_count     integer     not null default 0,
  add column if not exists last_follow_up_at   timestamptz;

-- Index for the daily follow-up scanner. Filters on (is_positive, stage,
-- follow_up_count) then orders by last_follow_up_at to find leads due for
-- a ping. At low volume this is cheap; keeping the index ahead of growth.
create index if not exists outreach_replies_followup_due_idx
  on public.outreach_replies (is_positive, stage, follow_up_count, last_follow_up_at);
