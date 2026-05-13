# DivineCore — AI Operating System

DivineCore is DivineSide's internal AI Operating System. Five autonomous modules run business functions end-to-end. This repo contains all agent definitions, workflow exports, knowledge base tooling, and infrastructure config.

---

## The Five Modules

### Module 1 — Branding OS
Full content pipeline from idea to publish-ready output.

| Agent | Role |
|-------|------|
| IMAGYN | Idea generation — pulls from Kallaway KB + working examples |
| LYRA | Script writing — emotional resonance, story structure |
| MONTAGE | Editing brief — b-roll, pacing, music, transitions |
| FORGE | Visual prompt generation for diffusion models (Midjourney, Runway, Flux) |
| VIGIL | Performance feedback loop — Instagram Graph API + YouTube Analytics |

Knowledge base:
- **Airtable** — Kallaway framework lessons (51+ entries, exact retrieval)
- **Supabase + pgvector** — Working content examples, semantic search via OpenAI embeddings

### Module 2 — Sales OS
Active pipeline management and outbound. Initiates contact, sends follow-ups, tracks deals.

Agents: Lead Agent, Follow-up Agent, Deal Agent  
Knowledge base: Alex Hormozi $100M series — offer construction, lead conversion, pipeline frameworks

### Module 3 — Ops OS
Gap detection and manual escalation. When any pipeline reaches a step requiring human intervention, Ops OS detects it and alerts the right person immediately.

Agents: Task Agent, Reminder Agent, Monitoring Agent

### Module 4 — Pulse
Alert and accountability layer. Runs across all module channels simultaneously.

- Morning digest at 03:30 IST
- Progressive deadline reminders
- Breach detection and escalation
- Admin commands via private #pulse channel

Model: GPT-4o mini via OpenRouter  
Task database: Airtable — DivineCore base, Task table

### Module 5 — Networking & Recruitment OS
Automates outreach and recruiting at scale across platforms.

Current: YouTube comment bots, Discord server bots  
Expanding to: LinkedIn, Reddit, Skool, WhatsApp

---

## Tech Stack

| Layer | Tool | Notes |
|-------|------|-------|
| Interface | Discord | Primary operating environment |
| Workflow / Orchestration | n8n | Self-hosted on Hostinger VPS |
| AI Models | Anthropic Claude, OpenAI GPT-4o mini | Via OpenRouter as fallback |
| Database (structured) | Airtable | Task tracking, CRM, knowledge bases |
| Database (vector) | Supabase + pgvector | Semantic search for working examples |
| Embeddings | OpenAI text-embedding-3-small | Supabase vector store |
| Discord Middleware | Node.js (discord.js) | Bridges Discord → n8n webhooks |
| VPS | Hostinger | srv1445995.hstgr.cloud |
| Process Manager | PM2 | Keeps middleware alive |
| Reverse Proxy | Nginx | HTTPS routing on VPS |

---

## Repo Structure

```
DivineSide/
├── CLAUDE.md                  ← Full AI context file (for Claude Code)
├── README.md                  ← This file
├── branding_os/               ← Module 1: Creative Intelligence
│   ├── agents/                ← Agent definitions and system prompts
│   ├── knowledge-base/        ← KB management scripts
│   └── workflows/             ← n8n workflow exports (JSON)
├── sales_os/                  ← Module 2: Revenue System (Upwork integration live)
│   ├── agents/
│   ├── workflows/
│   ├── integrations/upwork/   ← Celery tasks for proposal generation
│   └── web/                   ← FastAPI router + templates for /upwork
├── ops_os/                    ← Module 3: Execution System (Fathom integration live)
│   ├── agents/
│   ├── workflows/
│   └── integrations/fathom/   ← Celery poller + processor
├── pulse/                     ← Module 4: Alert + Awareness
│   ├── agents/
│   └── workflows/
├── networking_os/             ← Module 5: Networking & Recruitment
│   ├── agents/
│   ├── bots/
│   └── workflows/
├── infrastructure/            ← VPS, middleware, Discord bot, nginx configs
│   └── discord-middleware/
└── shared/                    ← Shared utilities, base classes, common tools
    └── utils/
```

---

## Working Conventions

- **One agent, one job.** Never combine responsibilities. Separate agents = less hallucination, lower cost, more precise outputs.
- **n8n handles orchestration.** Triggers, routing, inter-agent handoffs, scheduled workflows.
- **Commit workflow exports.** Every time an n8n workflow is updated, export the JSON and commit it to the relevant module folder.
- **Manual first, automate second.** Document the manual process before building automation.
- **Research drives architecture.** Every agent is backed by a defined knowledge base source.
- **Scope boundary.** This repo and Claude Code only touch DivineCore AIOS workflows. Client workflows (chatbots, appointment flows, payment flows) are separate and not managed here.

---

## Progress Tracking

All progress is tracked via git commit messages. Every commit describes what changed and what was updated — `git log` is the source of truth for what's been built and when.