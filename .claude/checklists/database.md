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

## General

- Never hardcode a table name, endpoint, or model name more than once, put it in a constant at the top of the file
- After any deploy, trigger the task once manually and read the logs immediately before calling it done
- If a log says `UndefinedTable` or `InvalidTextRepresentation`, the schema in Supabase doesn't match the code. Fix the schema first, then the code.
