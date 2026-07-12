# Pre-Build Checklist — Database & External APIs

Run through this before writing any code that touches a database or external API. Most bugs in this codebase have come from skipping these steps.

## Database (Supabase)

- Copy-paste the exact table name from the Supabase dashboard, never type it from memory
- Check every column name AND its type before writing an INSERT or SELECT
- Run the query manually in the Supabase SQL editor first and confirm it works
- Define new table schemas in SQL, commit them to the repo so the schema is documented alongside the code
- Column types matter: `text` for plain strings, `json`/`jsonb` only when storing actual JSON objects (mixing these causes runtime errors)

## External APIs (Discord, OpenAI, Anthropic, n8n, etc.)

- Read the actual API response before writing code that consumes it, never assume field names
- Test with a curl command or Postman before writing the integration
- Field name casing is exact: `channel_Id` is not `channel_id`. Copy from docs or a live response
- Confirm the endpoint URL is reachable from wherever the code runs (VPS Docker network is not localhost)

## Vector tables (pgvector / ivfflat)

- **`ivfflat` indexes bloat after heavy inserts+deletes and don't shrink on their own.** On Supabase's free tier (500MB cap), a table with far more rows in its index than in its actual data (check `pg_relation_size` on the index vs. the table) means the index needs a rebuild, not an upgrade.
- Fix: `DROP INDEX`, `VACUUM FULL <table>`, then recreate with `lists ≈ sqrt(row_count)`. Supabase free tier caps `maintenance_work_mem` at 32MB — if `CREATE INDEX` throws `ProgramLimitExceeded`, halve `lists` and retry until it fits.
- This does **not** hurt retrieval quality at small-to-medium row counts (tens of thousands of rows) — fewer `lists` means each partition is larger, so the default `probes=1` search actually scans a *bigger* share of the space, not a smaller one. It only becomes a real accuracy tradeoff at large row counts (100K+) where `lists` needs to scale with `probes` to keep query latency reasonable.
- Confirmed working 2026-07: a 592MB DB (over the free-tier cap) dropped to 197MB after rebuilding a bloated 389MB ivfflat index down to `lists=8` for 18K rows, with retrieval scores unchanged on the same test queries.
- **Below ~10k rows, use NO vector index at all.** An exact scan is <10ms with perfect recall; any ivfflat there is pure accuracy loss. Confirmed 2026-07-12: `pyq_chunks` (1,302 rows, `lists=50`, `probes=1`) searched ~2% of the space — real 0.42-sim matches never surfaced and the generate pipeline silently got zero PYQ examples. Dropping the index fixed retrieval instantly.

## General

- Never hardcode a table name, endpoint, or model name more than once, put it in a constant at the top of the file
- After any deploy, trigger the task once manually and read the logs immediately before calling it done
- If a log says `UndefinedTable` or `InvalidTextRepresentation`, the schema in Supabase doesn't match the code. Fix the schema first, then the code.
