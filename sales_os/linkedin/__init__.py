"""LinkedIn engage-first outreach pipeline (the §14 sequence).

Ports the local tools/outreach-tracker pipeline to Supabase: Tier A/B/C
prospects moving comment -> connect -> accept -> first msg -> loom -> engage,
with the 2-day comment-to-connect cadence. Table li_prospects. Shown as a tab
in /crm; API at /crm/api/li/*.
"""
