# DivineSide — Claude Code Context

This file gives Claude Code full context on DivineSide, DivineCore, the team, the tech stack, the business model, and the current state of the build. Read this before touching anything.
Refer to Information.md for additional knowledge.

## 1. COMPANY OVERVIEW

Company name: DivineSide  
Type: AI Operating System (AI OS) Agency  
One-liner: "DivineSide turns businesses into systems."  
Stage: Early — building, testing, getting first clients, finding distribution

Core philosophy:
- Traditional business: people execute, tools assist
- DivineSide model: systems execute, people supervise
- The shift: from doing work to designing systems

DivineSide is not an automation agency. We do not build chatbots and call them AI. We build fully autonomous operating systems that run entire functions of a business end-to-end. The machine executes. Humans supervise.


## 2. BUSINESS MODEL

**Stage 1 — Custom AI OS Builds (Current)**  
We build fully autonomous operating systems for client businesses. Each build runs an entire department or business function. Niche-agnostic for now — experimenting across industries to find patterns. Each build = cash flow + R&D simultaneously.

Running in parallel: commoditised solutions (chatbots, simple automations, SMS flows, lead capture) that feed the startup financially while deeper AI OS work develops.

**Stage 2 — GaaS: Agentic as a Service (Future)**  
After enough custom builds and niche discovery, we productise. Autonomous OS delivered as a subscription. What SaaS was 15 years ago — except instead of a tool, the client gets a system that runs a business function entirely. Product name not yet finalised. We earn our way here one build at a time.

DivineCore is the name for DivineSide's internal system only. The external product name is TBD.


## 3. DIVINECORE — INTERNAL BUSINESS OS

DivineCore is DivineSide's own Business Operating System. It is:
- NOT a product we sell
- NOT marketed externally
- The internal proof of concept — runs the agency itself
- The architecture template for all client builds

Every system we build for clients is derived from architecture first proven in DivineCore.

**Primary Interface**  
Discord — real-time, bot-native, structured by channel as department. Agents live as Discord bots. Each module has its own channel. Admin commands go through a private #pulse channel.

Discord Server: DivineSide | Server ID: 1489255611857371266

DivineCore channels:
- #branding — ID: 1495654627322892319
- #sales-and-outreach — ID: 1495654885218189392
- #recruitment-and-networking — ID: 1495655231013519422
- #operations — ID: 1495655877900763186
- #pulse — private admin channel
- #deploys — CI/CD status notifications from divinecore-v2 GitHub Actions (webhook configured in repo secrets as `DISCORD_WEBHOOK_URL`)


## 4. TECH STACK

| Layer | Tool | Notes |
|-------|------|-------|
| Interface | Discord | Primary operating environment |
| Automation/Workflow | n8n | Self-hosted on Hostinger VPS |
| Development | Claude Code | Primary and increasingly dominant dev tool |
| AI Models | Anthropic (Claude), OpenAI (GPT-4o mini) | Via OpenRouter as fallback |
| Database (structured) | Supabase | Knowledge bases, task tracking, CRM |
| Database (vector) | Supabase + pgvector | Semantic search for working examples |
| Embeddings | OpenAI text-embedding-3-small | For Supabase vector store |
| Middleware | Node.js (discord.js) | Discord → n8n webhook bridge |
| VPS | Hostinger | srv1445995.hstgr.cloud / IP: 187.124.96.99 |
| Process Manager | PM2 | Keeps middleware alive, survives reboots |
| Reverse Proxy | Nginx | HTTPS routing on VPS |
| Future Interface | Proprietary app (TBD) | Replaces Discord when DivineSide launches publicly |

**n8n Instance**  
URL: https://n8n.srv1445995.hstgr.cloud  
Hosted on Hostinger VPS. All workflows live here.

**Discord Middleware**  
Location on VPS: /root/discord-middleware/index.js  
Forwards Discord messages to n8n webhooks  
Server webhook: 16202f28-06f5-4d4a-8060-97dcd9986c3b  
DM webhook: d0ecdaad-f267-4fd5-8719-36ffe007067f  
PM2 commands: pm2 start/restart/logs discord-middleware

**Code Stack Direction**  
Claude Code is the primary build tool going forward. Python scripts for agents, tools, and system logic live in this GitHub repo. n8n handles orchestration and workflow triggers. Claude Code handles everything that requires real code — custom logic, API integrations, agent tool definitions, data processing.



## 6. THE TEAM

DivineSide is run by **3 co-founders**. Detailed ownership and KPIs are being formalized in the May 2026 alignment meeting — this section will be updated post-meeting to reflect locked decisions.

| Name | Role | Notes |
|------|------|-------|
| Mayank Rawat | Co-founder · CEO, Engineering, Video Content | Owns product vision, system architecture, founder-led sales, all video content. Discord: mayank082527 |
| Shubham | Co-founder · Research & Ops | Owns Kallaway/Hormozi knowledge bases, pre-call audits, operational support |
| Pang (彭毅和) | Co-founder · Developer + Marketing | CS at Wuhan University, China. Owns pilot delivery, outbound engine, divinecore-v2 stack |


## 10. ACCOUNTS & CREDENTIALS REFERENCE

Do not store passwords or API keys in this file. Reference only.

**External services**
- n8n: https://n8n.srv1445995.hstgr.cloud
- VPS: srv1445995.hstgr.cloud | IP: 187.124.96.99
- Airtable base: DivineCore
- Primary email (old): mayankrawat000072@gmail.com

**VPS SSH access** (`root@srv1445995.hstgr.cloud`)
- Pang (`yhpang@oneboxagency.com`) — authorized 2026-05-03. ed25519 key, no passphrase, generated on his Windows laptop at `C:\Users\user\.ssh\id_ed25519`. Personal access; CI auto-deploy will use a separate key when wired up.
- To grant or revoke a teammate's SSH access: edit `/root/.ssh/authorized_keys` on the VPS (one public key per line, comment field identifies the person).

**GitHub repository — `OneBox69/AIOS-DivineCore`** (Pang's fork, primary working repo)
- Upstream `DivineSide/AIOS-DivineCore` is currently stale; all active work happens on the fork.
- GitHub Actions secrets:
  - `GITHUB_TOKEN` — auto-provisioned, used to push images to GHCR.
  - `DISCORD_WEBHOOK_URL` — webhook for `#deploys` channel. Configured 2026-05-03.

**GitHub Container Registry (`ghcr.io/onebox69/aios-divinecore/{api,worker}`)**
- Images are **private**. Pulling requires auth.
- A classic PAT with `read:packages` scope only is cached on the VPS at `/root/.docker/config.json` (set up 2026-05-03 via `docker login ghcr.io -u onebox69 --password-stdin`). Rotate on PAT expiration.
- Anyone else pulling these images on a new machine needs to either be invited as a collaborator or generate their own `read:packages` PAT.


## 11. REPOSITORY STRUCTURE CONVENTIONS

```
DivineSide/
├── CLAUDE.md                  ← This file. Always keep updated.
├── README.md                  ← Public-facing repo overview
├── .env.example               ← Environment variable template (no real values)
├── branding_os/               ← Module 1: Creative Intelligence
│   ├── agents/                ← Agent definitions and system prompts
│   ├── knowledge-base/        ← KB management scripts
│   ├── workflows/             ← n8n workflow exports (JSON)
│   └── README.md
├── sales_os/                  ← Module 2: Revenue System
│   ├── agents/
│   ├── workflows/
│   ├── integrations/          ← Domain integrations (Upwork live)
│   │   └── upwork/            ← Celery tasks (proposal generation + sheet finalize)
│   └── web/                   ← FastAPI routers + Jinja templates mounted by divinecore-v2/api
│       └── upwork_routes.py + templates/
├── ops_os/                    ← Module 3: Execution System
│   ├── agents/
│   ├── workflows/
│   └── integrations/          ← Domain integrations (Fathom live)
│       └── fathom/            ← Celery poller + processor + tasks_writer
├── pulse/                     ← Module 4: Alert + Awareness
│   ├── agents/
│   ├── workflows/
│   └── README.md
├── networking_os/             ← Module 5: Networking & Recruitment
│   ├── agents/
│   ├── bots/
│   ├── workflows/
│   └── README.md
├── divinecore-v2/             ← Code-first runtime (FastAPI + Celery + Redis + compose)
│   ├── api/                   ← Generic FastAPI app; mounts routers from <module>/web/
│   └── worker/                ← Celery wiring + scheduled jobs; loads tasks from <module>/integrations/
├── infrastructure/            ← VPS, middleware, Discord bot, nginx configs
│   ├── discord-middleware/
│   └── README.md
└── shared/                    ← Shared resources used across modules
    ├── context/               ← Cross-module identity context (business-info, mayank, pang, voice, strategy, audience, linkedin-playbook). Every writing agent loads from here.
    ├── utils/                 ← Shared utilities, base classes, common tools
    └── README.md
```

**Folder naming**: module folders use Python-import-safe underscores (`sales_os/`, `branding_os/`, `ops_os/`, `networking_os/`, `pulse/`) so the divinecore-v2 runtime can import code from them as packages. Hyphens are reserved for non-Python directories (`divinecore-v2/`, `knowledge-base/`).

**Code vs n8n split**: each module folder mixes Python code (`integrations/`, `web/`, `agents/`), n8n workflow JSONs (`workflows/`), and KB sync scripts (`knowledge-base/`). The runtime that *executes* the Python lives in `divinecore-v2/`; the modules host their own logic and get imported.


## 12. WORKING CONVENTIONS

- **Claude Code is the primary development tool.** Use it for all Python, scripting, agent logic, and complex custom builds.
- **n8n handles orchestration.** Triggers, routing, inter-agent handoffs, scheduled workflows. Export workflow JSONs to /module/workflows/ for version control.
- **One agent, one job.** Never combine responsibilities into a single agent. Separate agents = less hallucination, lower API cost, more precise outputs, faster execution.
- **Manual first, automate second.** Never automate a workflow that hasn't been run manually enough to understand all edge cases. Document the manual process first, then build from it.
- **Research drives architecture.** Before building any agent, define its knowledge base source. The agent is only as good as the research fed into it.
- **Mayank assigns tasks. System tracks everything after.** Task assignment is always manual and intentional. Automation handles reminders, tracking, and escalation.
- **Commit workflow exports.** Every time an n8n workflow is updated, export the JSON and commit it to the relevant module folder.
- **Writing agents load from `shared/context/`.** Any agent producing copy aimed at humans (sales emails, LinkedIn posts, YouTube scripts, DMs, follow-ups) MUST pull from `shared/context/` in addition to its domain KB. Brand-level files: `business-info.md`, `voice.md`, `strategy.md`, `audience.md`. Per-person persona files: `mayank.md`, `pang.md` (load whichever team member the content is voiced as). Channel-specific tactical playbooks: `linkedin-playbook.md` (more to come). CLAUDE.md is for system architecture; `shared/context/` is for brand voice. Don't duplicate identity content into module folders — reference it.


## 13. PRE-BUILD CHECKLIST — DATABASE & EXTERNAL APIs

Run through this before writing any code that touches a database or external API. Most bugs in this codebase have come from skipping these steps.

**Database (Supabase)**
- Copy-paste the exact table name from the Supabase dashboard — never type it from memory
- Check every column name AND its type before writing an INSERT or SELECT
- Run the query manually in the Supabase SQL editor first and confirm it works
- Define new table schemas in SQL, commit them to the repo so the schema is documented alongside the code
- Column types matter: `text` for plain strings, `json`/`jsonb` only when storing actual JSON objects — mixing these causes runtime errors

**External APIs (Discord, OpenAI, Anthropic, n8n, etc.)**
- Read the actual API response before writing code that consumes it — never assume field names
- Test with a curl command or Postman before writing the integration
- Field name casing is exact: `channel_Id` ≠ `channel_id`. Copy from docs or a live response
- Confirm the endpoint URL is reachable from wherever the code runs (VPS Docker network ≠ localhost)

**General**
- Never hardcode a table name, endpoint, or model name more than once — put it in a constant at the top of the file
- After any deploy, trigger the task once manually and read the logs immediately before calling it done
- If a log says `UndefinedTable` or `InvalidTextRepresentation` — the schema in Supabase doesn't match the code. Fix the schema first, then the code.


