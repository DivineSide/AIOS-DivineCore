# Comprehensive information about DIVINESIDE AI and Divinecore.
##  THE RESEARCH PHILOSOPHY — THE CORE MOAT

The product is not built around tools. It is built around research.

Each DivineCore module is fed the encoded knowledge, frameworks, and mental models of the best practitioners in that domain. This is the competitive defensibility. No enterprise tool can replicate this because they build features — we build expertise into the system.

When the underlying tools change (and they will), the research and domain intelligence remains.

Current knowledge bases:

| Module | Source | Format |
|--------|--------|--------|
| Branding OS | Kallaway (YouTube creator — best research on content creation) | Airtable (exact retrieval) + Supabase (semantic search) |
| Sales OS | Alex Hormozi — $100M Offers + $100M Leads books | Supabase (structured frameworks) |

Research workflow: watch source material → Tactiq transcription → Glasp highlights → paste into Claude Research project → extract structured lessons → enter into Airtable.

##. DISTRIBUTION — CURRENT STATE

Primary: Mayank's personal network. Warm relationships, direct conversations, trusted introductions. Highest-conversion channel at this stage.

Secondary: Direct outreach — team executing manually via DMs, LinkedIn, targeted conversations. Cold calling being introduced shortly.

Sales OS will handle outreach autonomously as it matures — the team sets strategy, the system executes volume.

Long-term engine: Brand. Building in public across YouTube and Instagram. Almost nobody is building AI OS systems at this level AND documenting it publicly. That is the positioning edge. Once Branding OS is fully operational, content production is largely automated — distribution becomes self-sustaining.

## 14. DIVINECORE V2 — CODE-FIRST RUNTIME (IN BUILD)

Parallel track to the n8n-orchestrated stack. `divinecore-v2/` is the **runtime only** — FastAPI app, Celery worker, Beat scheduler, Redis broker, Docker compose. Domain code (Upwork, Fathom, future module integrations) lives in the module folders (`sales_os/`, `ops_os/`, etc.) and is imported by the runtime at build time. Both Dockerfiles set context = repo root and selectively `COPY` the module folders they need.

### Foundation (commit `3c03553`)

Stack: **FastAPI API + Celery worker + Celery Beat scheduler + Redis broker**, all in Docker Compose.

```
divinecore-v2/
├── api/                       ← FastAPI service (runtime only)
│   ├── main.py                ← Inline / + /tasks routes; imports + mounts routers from <module>/web/
│   ├── settings.py            ← Pydantic Settings (REDIS_URL)
│   ├── requirements.txt
│   └── Dockerfile             ← context = repo root; copies api/ + sales_os/
├── worker/                    ← Celery worker + beat (shares same image, runtime only)
│   ├── celery_app.py          ← Celery config + beat_schedule + include=[...] paths into modules
│   ├── tasks.py               ← echo, heartbeat (generic infra tasks)
│   ├── settings.py            ← Pydantic Settings (Supabase, OpenRouter, Fathom, Google OAuth, Redis)
│   ├── team.py                ← TEAM_MEMBERS dict + email/name lookup
│   ├── requirements.txt
│   └── Dockerfile             ← context = repo root; copies worker/ + sales_os/ + ops_os/
├── docker-compose.yml         ← local dev — context: .., volume mounts of api/, worker/, sales_os/, ops_os/, hot-reload
└── docker-compose.prod.yml    ← VPS deploy (image: from GHCR, no volume mounts, restart: unless-stopped, API behind Traefik basicauth)
```

Domain code mounted into the containers (lives outside `divinecore-v2/`):
- `sales_os/integrations/upwork/` — Upwork pipeline (Celery tasks)
- `sales_os/web/upwork_routes.py` + templates — `/upwork` UI mounted into FastAPI
- `ops_os/integrations/fathom/` — Fathom poller + processor (Celery tasks)

A repo-root `.dockerignore` trims build context size since context is now the whole repo.

Services in compose:
- `redis` — `redis:7-alpine`, exposes 6379
- `api` — FastAPI on `:8000`, talks to Celery via `REDIS_URL`
- `worker` — Celery worker, processes tasks from Redis
- `beat` — Celery Beat, runs scheduled tasks (currently `tasks.heartbeat` every 30s)

Endpoints today:
- `GET /` — health
- `POST /tasks/echo` — submit a task, returns `task_id`
- `GET /tasks/{task_id}` — poll status + result
- `GET /upwork` — Upwork proposal generator form (paste a job description). **Public**: https://upwork.srv1445995.hstgr.cloud/upwork (basic auth gated)
- `POST /upwork` — runs the Upwork pipeline (2 OpenRouter LLM calls + Google Docs/Drive/Sheets), blocks on result, renders application body + proposal Doc URL + a finalize form for connects/Loom
- `POST /upwork/finalize` — patches base+boosted connects ("15 + 5") and Loom URL into the existing tracking-sheet row

Run locally: `cd divinecore-v2 && docker compose up --build`. Public access details below in *Phase 2 → Public endpoints*.

### Integrations

- **Fathom** — beat polls Fathom's REST API every 10 min, writes new meetings to Supabase's `meetings` table, and creates Pulse task rows for action items assigned to opted-in team members. No public ingress required — fully outbound. **Lives in `ops_os/integrations/fathom/`** (Celery tasks `tasks.poll_fathom_recordings` etc., loaded by `divinecore-v2/worker/celery_app.py` `include=[...]`). See [ops_os/integrations/fathom/.overview.md](ops_os/integrations/fathom/.overview.md).
- **Upwork** — user-initiated via `GET /upwork` form. Originally migrated from a 3-workflow n8n system; the per-job sales-script Doc + Mermaid diagram step was dropped (Pang uses one standardised sales script across all calls; the Loom carries the AIOS framing). Today's pipeline: 2 OpenRouter LLM calls (proposal fields, application copy) + Google Docs/Drive/Sheets to copy the proposal template, mail-merge, share, and append to a tracking sheet. **Lives in `sales_os/integrations/upwork/`** (Celery tasks) + `sales_os/web/upwork_routes.py` (FastAPI router). About-Me content lives in `sales_os/integrations/upwork/about_me.py` — Upwork-specific, intentionally stripped of "co-founder" / "agency" framing (some buyers are agency-averse); loosely derived from [shared/context/pang.md](shared/context/pang.md) but **not** an auto-mirror — edit directly when needed. Application body prompt enforces the AIOS framing (verbatim sentence: *"I don't build commoditized automations. I build AI Operating Systems — your business, running on AI."*) — this deliberately diverges from sales-playbook.md line 173 ("never lead with AIOS externally") because on Upwork specifically AIOS is the differentiator that justifies the price floor. Google auth via OAuth refresh token — one-time bootstrap with `docker compose run --rm worker python -m sales_os.integrations.upwork.oauth_bootstrap`. Env vars: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`, plus optional `UPWORK_*` model/template-ID overrides. See [sales_os/integrations/upwork/.overview.md](sales_os/integrations/upwork/.overview.md).
- **Instantly** — cold-email outreach (current positioning: *UK ecom beauty 5–50 employees*). Webhook ingress at public `POST /instantly/webhook` validates a shared `X-Webhook-Secret` header and enqueues a Celery task that stores meaningful replies (skipping OOO/auto-replies) to Supabase `outreach_replies` and pings the `outreach-replies` thread inside `#sales-and-outreach` for any reply Instantly's AI labels positive (configurable set in `categories.py`). **No LLM classification on our side** — we trust Instantly's labels. **No per-email-send rows** — a daily 00:30 UTC Celery beat task (`tasks.poll_instantly_campaigns`) snapshots Instantly's campaign + step analytics into `outreach_daily_step_metrics` (one row per campaign × step × day). Operator owns `outreach_campaigns.positioning` (set manually in Supabase Studio after the first poll lands the row; the poller's upsert never overwrites it). Reporting dashboard lives at `GET /outreach` (basicauth) — campaign list + per-campaign drill-in with per-step / daily / lifetime metrics + recent replies feed. **Lives in `sales_os/integrations/instantly/`** (Celery tasks + Supabase + Discord) + `sales_os/web/instantly_routes.py` (webhook + dashboard). Traefik routes the public webhook via a separate router (`instantly-webhook` priority 100) that bypasses the basicauth middleware applied to the rest of `upwork.srv1445995.hstgr.cloud`. Env vars: `INSTANTLY_API_KEY`, `INSTANTLY_WEBHOOK_SECRET`, `DISCORD_OUTREACH_WEBHOOK_URL`, `DISCORD_OUTREACH_THREAD_ID`, plus optional `INSTANTLY_API_BASE_URL`. See [sales_os/integrations/instantly/.overview.md](sales_os/integrations/instantly/.overview.md).

### CI/CD Workflow (commit `3573662`)

File: `.github/workflows/divinecore-v2-ci.yml`

Triggers: push/PR to `main` (path-filtered to `divinecore-v2/**`, `sales_os/**`, `ops_os/**`, and the workflow file itself) + `workflow_dispatch`.

**Build & push job** (matrix: `api`, `worker`):
- Runs both components in parallel via matrix strategy
- Build context is the repo root; `dockerfile:` matrix entry points at `divinecore-v2/{api,worker}/Dockerfile`
- Uses `docker/setup-buildx-action@v3` + `docker/build-push-action@v6`
- Pushes to `ghcr.io/onebox69/aios-divinecore/{api,worker}`
- Tags: `:latest` (main only), `:sha-<short>`, `:<branch>`
- GHA cache scoped per component (`cache-from/to` with `scope=${name}`) — fast incremental rebuilds
- PRs are build-only (no push to GHCR, no Discord ping) — gated on `github.event_name != 'pull_request'`

**Notify job:**
- Runs after `build-and-push` on push + workflow_dispatch (excludes PR builds — see PR #2)
- Uses `sarisia/actions-status-discord@v1`
- Posts status embed (success/failure) to `#deploys` via `DISCORD_WEBHOOK_URL` secret
- Embed includes branch + commit message

Required GitHub secrets:
- `GITHUB_TOKEN` — provided automatically, used for GHCR auth
- `DISCORD_WEBHOOK_URL` — webhook for `#deploys` channel (configured on `OneBox69/AIOS-DivineCore`, end-to-end verified 2026-05-03)

Permissions on the build job: `contents: read`, `packages: write` (needed to push to GHCR).

### Phase 2 — Deployed (manual deploy live, auto-deploy still pending)

The stack is **running on the Hostinger VPS** at `/root/divinecore-v2/` as of 2026-05-03. Deployed manually over SSH; CI does not yet auto-deploy on merge.

**What's running on the VPS:**
- `divinecore-v2-redis-1` — internal compose network only, no port exposure
- `divinecore-v2-api-1` — FastAPI on port 8000 (no host port binding); attached to `divinecore` bridge AND `n8n_default` external network so n8n's Traefik can route to it
- `divinecore-v2-worker-1` — Celery worker, connected to Redis
- `divinecore-v2-beat-1` — Celery Beat, scheduling `tasks.heartbeat` every 30s
- All four `restart: unless-stopped`, isolated from n8n's containers via dedicated `divinecore` bridge network (api additionally joins `n8n_default` for Traefik discovery)

**GHCR auth on VPS:** `docker login ghcr.io` configured with a GitHub PAT (`read:packages` scope only). Credentials cached in `/root/.docker/config.json` — required for pulling private images on each `docker compose pull`. Rotate the PAT on its expiration.

**Manual deploy procedure** (from local laptop):
```
ssh root@srv1445995.hstgr.cloud "cd /root/divinecore-v2 && docker compose pull && docker compose up -d"
```

**Smoke test verified:** `POST /tasks/echo` → task queued in Redis → worker processes → `GET /tasks/{id}` returns `SUCCESS` with uppercased result. Full async pipeline working end-to-end on VPS.

### Public endpoints

**`/upwork` is live publicly** at `https://upwork.srv1445995.hstgr.cloud/upwork` (deployed 2026-05-04). Routed through n8n's existing Traefik (the only reverse proxy on the VPS — `n8n-traefik-1`, ports 80/443).

Wiring:
- The api service in `docker-compose.prod.yml` carries `traefik.*` labels (Host rule, `websecure` entrypoint, `tls=true`, basicauth middleware). Traefik picks them up via Docker socket events.
- api is attached to the external `n8n_default` network (declared at compose bottom as `networks.traefik`) — that's how Traefik reaches the container.
- **Basic auth** via `traefik.http.middlewares.upwork-auth.basicauth.users` label. Bcrypt hash inline, dollar signs escaped as `$$` per compose syntax. Username/password live in your password manager — to rotate, generate a new hash with `docker run --rm httpd:2.4-alpine htpasswd -nbB <user> <pass>`, double the `$`, replace the label, push, redeploy.
- **TLS cert is Traefik's default self-signed.** Browser shows a one-time "Not secure" warning per device — click through, browser remembers the exception. Reason: Let's Encrypt rate-limited the `*.hstgr.cloud` apex (25k certs in 7d, shared across all Hostinger users on the domain), so `tls.certresolver=mytlschallenge` returned `429 rateLimited` and was removed. To upgrade to a real cert: migrate to a domain outside the rate-limited apex (~$1–12/yr for a `.xyz`/`.com`), or wait for LE quota to roll over, then re-add the certresolver label.

n8n's `web` (HTTP) entrypoint has a global `--entrypoints.web.http.redirections.entryPoint.to=websecure` set in Traefik's command line — all HTTP traffic gets 308'd to HTTPS automatically. This is shared with n8n; don't change it without auditing n8n impact.

**Still pending:**
- **Auto-deploy from CI.** Add a `deploy` job to `divinecore-v2-ci.yml` that SSHes into VPS after each successful `build-and-push` on main and runs the manual deploy command above. Needs a separate deploy SSH keypair + 3 GitHub secrets (`VPS_SSH_PRIVATE_KEY`, `VPS_HOST`, `VPS_USER`). Mayank's personal SSH key is already authorized on the VPS as of 2026-05-03; CI will use a different key.
- **Trusted TLS cert for upwork.* subdomain.** Currently default self-signed (browser warning). Upgrade path: switch to a domain outside `hstgr.cloud`, OR retry LE periodically.


## 14. CLAUDE CODE SLASH COMMANDS

Project-scoped slash commands live in `.claude/commands/` and are version-controlled. Each `.md` file becomes an invocable command (e.g. `prime.md` → `/prime`).

| Command | Purpose |
|---------|---------|
| `/prime` | Load full DivineCore context at session start. Reads `CLAUDE.md` + `README.md`, lists `divinecore-v2/`, runs `git log --oneline -20`, and reads `.claude/session.md` if present. Ends with a briefing on active modules, v2 stack state, and recent commit activity. Use this at the top of any non-trivial session. |
| `/resume` | Lightweight re-entry. Reads `CLAUDE.md` (and `.claude/session.md` if present) and gives a one-paragraph briefing: what was done last session, current state, single next action. |
| `/save-context` | Writes a ≤300-word session summary to `.claude/session.md` covering what changed, current state, decisions made, and the next step to resume from. Note: per commit `13faee3` we now lean on `git log` for progress tracking, so this is optional — use it only when the in-flight state genuinely won't be obvious from commit history. |

When adding new commands, keep them small and composable. One command, one job — same rule as agents.


## 15. TIERED CONTEXT CONVENTION (L0/L1/L2)

Inspired by ByteDance's OpenViking pattern. Every folder in this repo carries cheap, tiered context so an agent can scan the whole tree without paying full-file token costs.

| Tier | File | Size | When to load |
|------|------|------|--------------|
| **L0** | `.abstract.md` | ~1 line (max ~150 chars) | Always — reading every `.abstract.md` in the repo should fit in ~2k tokens. Answers "what is this folder for?" |
| **L1** | `.overview.md` | ~50–200 lines | When the L0 abstract suggests this folder is relevant. Covers structure, status, key files, conventions, what NOT to put here |
| **L2** | actual files | full content | Only when actively working in the folder |

### Rules

- **Every folder gets `.abstract.md`.** No exceptions, except:
  - Anything gitignored or tooling-internal (`.git/`, `__pycache__/`, `node_modules/`, `.venv/`).
  - `.claude/commands/` — Claude Code registers every `.md` file in that folder as a slash command, so `.abstract.md` would become a phantom `/.abstract` command. The folder itself is small enough to scan directly.
- **L1 `.overview.md` is selective.** Only for folders with real content, strategic importance, or non-obvious structure. Empty leaf scaffolds (`branding_os/agents/` while it's just a `.gitkeep`) get the abstract only — an overview would be noise.
- **Promote to L1 when the folder has 3+ files OR when the structure isn't self-explanatory.**
- **Update on change.** When you add/remove/rename meaningful content in a folder, update its `.abstract.md` and `.overview.md` in the same commit. Stale L0/L1 is worse than missing L0/L1.
- **Don't duplicate CLAUDE.md.** L0/L1 should describe local file structure, not repeat company-wide architecture. Architecture lives here in CLAUDE.md.

### AGENT BEHAVIOUR — MUST FOLLOW

These are not suggestions. Any agent (Claude Code, subagent, future tooling) working in this repo MUST follow them.

**On WRITE — when creating or modifying folder structure:**

1. **Creating a new folder?** In the same operation, create its `.abstract.md` (one line, max ~150 chars, "what is this folder for"). Do not commit a folder without its abstract — that breaks the L0 scan invariant.
2. **Adding 3+ real files to a folder, or making its structure non-obvious?** Add a `.overview.md` (50–200 lines: status, key files, conventions, what NOT to put here).
3. **Renaming or repurposing a folder?** Update its `.abstract.md` and any `.overview.md` in the same commit. Stale L0/L1 is worse than missing.
4. **Deleting a folder?** The `.abstract.md` and `.overview.md` go with it — never leave orphaned dotfiles.
5. **Skip only**: gitignored / tooling-internal folders (`.git/`, `__pycache__/`, `node_modules/`, `.venv/`) and `.claude/commands/` (would register as a slash command).

**On READ — when searching, exploring, or answering questions about the repo:**

1. **Start with `.abstract.md` files.** Glob `**/.abstract.md` and read them all. This costs ~2k tokens and gives you a complete repo map. Do this BEFORE any broad grep, file read, or directory listing.
2. **Drill into `.overview.md`** for any folder the abstracts flagged as relevant. Do not jump straight to L2 file contents.
3. **Open actual files (L2) only** in the folders the overviews confirmed are relevant.
4. **For known-path lookups** (you already know the file you need), skip L0/L1 and read the file directly — the tiered scan is for *open-ended* search, not targeted reads.

This keeps `/prime`-style context loads cheap and lets subagents do narrow lookups without ingesting the whole repo. Violating the L0-first rule on open-ended search wastes tokens — treat it as a bug.

## 9. CONTENT & SOCIAL STRATEGY

Platforms: YouTube + Instagram (primary), LinkedIn + Reddit (secondary)  
Cadence: Minimum one piece of content per day  
Content types: Long-form video, short-form video, carousels, tweets/text posts, images

Content categories:
- Journey — what we're building, what's working, what isn't. Raw and honest.
- Lessons and insights — practical, not just inspirational
- DivineSide as AI OS agency — behind-the-scenes builds
- Client work — case studies, testimonials, results
- Business lessons — for founders and entrepreneurs

Positioning: We are not competing with generic creators. We are attracting founders, entrepreneurs, and operators who understand AI is infrastructure, not a tool. Build in public. Show wins and failures. Teach as we learn.

Monetisation layers:
- Custom AI OS builds (primary lead gen from content)
- Brand deals + advertisements
- Community + premium access (free community → paid upsells)
- Coaching + consulting (high ticket, accelerator-style)
- One-on-one coaching
