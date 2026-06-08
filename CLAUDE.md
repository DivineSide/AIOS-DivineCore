# DivineSide — Claude Code Context

This file gives Claude Code full context on DivineSide, DivineCore, the team, the tech stack, the business model, and the current state of the build. Read this before touching anything.

> **NICHE LOCKED 2026-06-06.** DivineSide targets **education and coaching businesses (exam-prep / coaching institutes)**, a pure-information business chosen for its structural fit with the AIOS context-learning moat plus a warm beachhead client. See [shared/context/identity/business-info.md](shared/context/identity/business-info.md) and the discovery note [shared/context/conversations/2026-06-05-beachhead-coaching-owner-call.md](shared/context/conversations/2026-06-05-beachhead-coaching-owner-call.md).
>
> **Locked, will not change:** the niche; the product vision (build complete AI Systems per client, harvest patterns into AIOS, never design AIOS up front); AIOS-is-the-moat-not-the-pitch (enter through painful manual functions); retainer delivery model; infrastructure / repo conventions.
>
> **Open, do NOT invent:** (1) the headline entry workflow, resolved in an upcoming **deep-research phase** (sketch from [shared/context/sales-and-delivery/offer.md §03](shared/context/sales-and-delivery/offer.md), do not lock); (2) the foreign target market (US vs UK); India is the prototype ground; (3) all pricing numbers.


## 1. COMPANY OVERVIEW

Company name: DivineSide  
Type: builder of complete AI Systems (deep, custom, vertical-first), harvesting a productized AI Operating System (AIOS) from delivery  
One-liner: "DivineSide turns businesses into systems."  
Stage: Early. Building, testing, getting first clients, finding distribution.

Core philosophy:
- Traditional business: people execute, tools assist
- DivineSide model: systems execute, people supervise
- The shift: from doing work to designing systems

DivineSide is not an automation agency. We do not build chatbots and call them AI, and we do not ship template GoHighLevel/Zapier workflows as the product. We build complete AI Systems that run business functions end to end and improve from the data the business already produces. The machine executes. Humans supervise.

### The product (the AI System) and the moat (AIOS)

An AI System has four layers: **Automation** (n8n/Make/Zapier, the nervous system), the **AIOS kernel** (the runtime: compounding memory, agent scheduling, tool access, and a syscall trust layer), **AI agents** (one job each), and the **LLM** (model-agnostic, used surgically). Two concepts make it non-commoditized: the **closed loop** (a thermostat, not a heater: observe, compare to target, self-correct without a human starting each step) and the **syscall trust layer** (agents never touch raw business data; they request through AIOS, which enforces permissions the owner set once).

We build complete AI Systems for one business at a time, and the patterns that repeat across builds get harvested into **AIOS**, our production platform. We do not design AIOS up front. We earn it from delivery. A pattern enters AIOS only after it shows up across multiple real builds: conviction is not evidence, delivery is. **AIOS is the moat, not the sales pitch.** We enter by solving a painful manual function; the intelligence layer builds underneath and compounds on the client's data. (Voice-shaped detail: [shared/context/identity/business-info.md](shared/context/identity/business-info.md).)


## 2. BUSINESS MODEL

**Harvest, do not design.** We build complete AI Systems for individual businesses, deepest pain first, and extract the patterns that repeat into the productized AIOS. The model is sequential: each phase has to be completed before the next becomes possible.

### The niche (locked 2026-06-06): education & coaching businesses

**Exam-prep / coaching institutes**, a pure-information business. Why this niche:

- **Domain edge.** The founders lived inside this world as students, and there is a warm beachhead client (an 8-year coaching-institute owner) who is a distribution channel, not just a customer (50+ convertible connections).
- **Structural fit with AIOS.** Coaching is the rare business where running the business and accumulating intelligence are the same activity. Every doubt asked, paper attempted, result recorded, and parent message is structured, reusable, causal context: exactly what a closed loop learns from. This is architectural, not a slogan.
- **Fragmented tooling, established budget.** Owners run 4 to 7 disconnected point tools (Classplus, Teachmint, Meritto, Proctur) and already pay for software. No unified closed-loop system exists.

**Geography:** India is the prototype ground (warm connections, fast access). The dream customers are Western (US/UK) coaching businesses with higher pricing power. **The specific foreign market is TBD.** Two-track GTM: Mayank + Shubham own India (Hindi, local trust); Pang owns foreign outreach (English).

### Phase 0 (NOW, weeks 1-4): Validate

Build the first AI System for an existing warm contact (a relative's coaching institute in India). Use it. Watch what breaks. **Goal: 2 paying clients in 4 weeks.** If we do not get there, revisit the niche, not the product vision.

- **Delivery model:** retainer (it replaces the manual-labor cost the owner already pays). **Pricing numbers are TBD and must not appear in docs or copy yet.**
- **The entry workflow is OPEN, pending a deep-research phase.** Candidates span four institute functions: Product (content/PPT/quiz generation, the beachhead's validated #1 pain), Marketing (results/testimonials/social proof), Customer Service (parent updates, doubt management, fee follow-up), Sales (do not lead here — Meritto/GoHighLevel own it). See [shared/context/sales-and-delivery/offer.md §03](shared/context/sales-and-delivery/offer.md). Do not lock a single lead workflow until the research lands.
- **We do NOT** pitch the productized system or AIOS, take clients outside the niche, or hard-commit pricing/entry-workflow/foreign-market before the research that decides them.

### Phase 1 (months 2-4): Go deep

Add the 2nd and 3rd workflows for the same clients. Agents share memory through the AIOS runtime layer that emerges underneath. Repeat the pattern for 2-3 more institutes. Document what is common across them.

### Phase 2 (months 5+): Earn the abstraction

The patterns that repeat across builds become the productized AIOS core. Widen to adjacent coaching verticals. Begin foreign-market expansion where pricing power is 5-10x higher.

### Phase 3 (later, optionality not plan): The platform

AIOS as a SaaS product, across verticals. **Only after the education vertical is proven.** This is never the starting point. Conviction is not evidence. Delivery is.

### Why this order matters

You cannot productize what you have not validated through real client work. A pattern enters AIOS only after it shows up across multiple real builds. **Custom builds during Phase 0-1 are not a detour from the product. They are the only path to it.** DivineCore is the internal system name; the external product name is TBD. (Full voice-shaped version: [shared/context/identity/business-info.md](shared/context/identity/business-info.md) and [shared/context/identity/strategy.md](shared/context/identity/strategy.md).)


## 2b. THE AIOS VISION

AIOS (AI Operating System) is the long-term SaaS product. It is **not a feature** in any individual client build — it is the runtime layer those builds run on, harvested into a product over time. This is the section every future Claude session loads to understand what we are building toward.

### What AIOS is, structurally

AIOS sits between the LLM and AI agents the same way a traditional OS sits between the CPU and apps. Same position, same job, different resource. It manages seven things:

- **LLM Core** — model-agnostic routing. Swap Claude for GPT-4 for DeepSeek in one config line. The system outlives any single model.
- **Agent Scheduler** — multiple agents run simultaneously without collision. No agent starves the others.
- **Memory Manager** — context that persists, compounds, and self-organises (A-MEM: agentic memory that connects new memories to existing ones and reorganises knowledge over time). This is the closed-loop foundation.
- **Storage Manager** — business knowledge navigated by natural language, not folder paths or database queries.
- **Tool Manager** — agents access external tools (CRMs, APIs, email, web) through a managed layer. One place, all integrations.
- **Access Manager (Syscall Trust Layer)** — agents never touch raw business data directly. They request through AIOS, which enforces permissions every time. This is the architectural answer to AI trust.
- **Context Manager** — long tasks stay coherent; agents do not lose the thread mid-workflow.

The reference implementation we study is the AIOS research repo from Rutgers (`agiresearch/AIOS`, published at COLM 2025). The architecture maps directly to traditional OS engineering — process scheduler → agent scheduler, syscall gateway → AIOS system call, kernel → AIOS kernel. Same engineering, applied to a new shared resource.

### The two core concepts that define AIOS

**1. The Closed Loop.** Every business today runs on open loops — they act, then check results weeks later, if ever. Information is produced and leaks. AIOS closes the loop: the system observes what is happening, compares to what should be happening, and adjusts continuously without human initiation. Thermostat vs heater. **Every business runs on heaters today. We sell thermostats.**

**2. The Syscall Trust Layer.** The reason businesses do not trust AI agents on real operations is that agents touch sensitive business data directly. AIOS solves this architecturally — the same way an OS solves it. Apps never touch hardware; they request through the kernel via a system call, and the kernel enforces what is allowed. We do the same for business data. The owner sets the rules once. The system enforces them every time.

These two concepts (closed loop + syscall trust layer) are what make AIOS non-commoditizable. They are also the two pieces nobody else has built properly.

### Why information businesses are the best first vertical

In a coaching institute, one doubt asked by a student is simultaneously a teaching-quality signal, a curriculum gap indicator, a student-profile data point, a predictor of exam performance, and a reusable pattern across future students. **The information IS the product.** Every operational action becomes a data point the closed loop can learn from. After 6 months of operation, AIOS knows more about how to teach that institute's students than any generic platform — and that accumulated intelligence is the moat. A competitor cannot copy it without starting from scratch. Intelligence accumulated over time is the moat — not features.

### How AIOS shows up in a sales conversation (it does not)

AIOS is the moat, not the pitch. Clients buy a solved problem — hours back, output doubled — not infrastructure. They experience the intelligence layer getting smarter over time without needing to understand why. The video script at [`Content/aios-video-script.md`](Content/aios-video-script.md) is the long-form public explainer for anyone who wants to understand what we are building underneath; **client-facing copy never leads with AIOS.**


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
| Database (structured) | Airtable | Knowledge bases, task tracking, CRM |
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


## 5. THE RESEARCH PHILOSOPHY — THE CORE MOAT

The product is not built around tools. It is built around research.

Each DivineCore module is fed the encoded knowledge, frameworks, and mental models of the best practitioners in that domain. This is the competitive defensibility. No enterprise tool can replicate this because they build features — we build expertise into the system.

When the underlying tools change (and they will), the research and domain intelligence remains.

Current knowledge bases:

| Module | Source | Format |
|--------|--------|--------|
| Branding OS | Kallaway (YouTube creator — best research on content creation) | Airtable (exact retrieval) + Supabase (semantic search) |
| Sales OS | Alex Hormozi — $100M Offers + $100M Leads books | Supabase (structured frameworks) |

Research workflow: watch source material → Tactiq transcription → Glasp highlights → paste into Claude Research project → extract structured lessons → enter into Airtable.


## 6. THE FIVE MODULES

**See** `[branding_os/.overview.md](branding_os/.overview.md)`, `[sales_os/.overview.md](sales_os/.overview.md)`, `[ops_os/.overview.md](ops_os/.overview.md)`, `[pulse/.overview.md](pulse/.overview.md)`, `[networking_os/.overview.md](networking_os/.overview.md)` for detailed breakdown of each module (agents, knowledge bases, capabilities, status).


## 7. THE TEAM

DivineSide is run by **3 co-founders**. Detailed ownership and KPIs are being formalized in the May 2026 alignment meeting — this section will be updated post-meeting to reflect locked decisions.

| Name | Role | Notes |
|------|------|-------|
| Mayank Rawat | Co-founder · CEO, Engineering, Video Content | Owns product vision, system architecture, founder-led sales, all video content. Discord: mayank082527 |
| Shubham | Co-founder · Research & Ops | Owns Kallaway/Hormozi knowledge bases, pre-call audits, operational support |
| Pang (彭毅和) | Co-founder · Developer + Marketing | CS at Wuhan University, China. Owns pilot delivery, outbound engine, divinecore-v2 stack |


## 8. DISTRIBUTION — CURRENT STATE

Primary: Mayank's personal network. Warm relationships, direct conversations, trusted introductions. Highest-conversion channel at this stage.

Secondary: Direct outreach — team executing manually via DMs, LinkedIn, targeted conversations. Cold calling being introduced shortly.

Sales OS will handle outreach autonomously as it matures — the team sets strategy, the system executes volume.

Long-term engine: Brand. Building in public across YouTube and Instagram. Almost nobody is building AI OS systems at this level AND documenting it publicly. That is the positioning edge. Once Branding OS is fully operational, content production is largely automated — distribution becomes self-sustaining.


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


## 10. ACCOUNTS & CREDENTIALS REFERENCE

**See infrastructure/README.md** for VPS access, GitHub repository configuration, GHCR auth, and deployment credentials. Do not store passwords or API keys in this file.


## 11. REPOSITORY STRUCTURE CONVENTIONS

**See [README.md](README.md)** for folder layout, naming conventions, code organization, and Python import structure.


## 12. WORKING CONVENTIONS

- **Claude Code is the primary development tool.** Use it for all Python, scripting, agent logic, and complex custom builds.
- **n8n handles orchestration.** Triggers, routing, inter-agent handoffs, scheduled workflows. Export workflow JSONs to /module/workflows/ for version control.
- **One agent, one job.** Never combine responsibilities into a single agent. Separate agents = less hallucination, lower API cost, more precise outputs, faster execution.
- **Manual first, automate second.** Never automate a workflow that hasn't been run manually enough to understand all edge cases. Document the manual process first, then build from it.
- **Research drives architecture.** Before building any agent, define its knowledge base source. The agent is only as good as the research fed into it.
- **Mayank assigns tasks. System tracks everything after.** Task assignment is always manual and intentional. Automation handles reminders, tracking, and escalation.
- **Commit workflow exports.** Every time an n8n workflow is updated, export the JSON and commit it to the relevant module folder.
- **Writing agents load from `shared/context/`.** Any agent producing copy aimed at humans (sales emails, LinkedIn posts, YouTube scripts, DMs, follow-ups, Loom scripts) MUST pull from `shared/context/` in addition to its domain KB. Organized into three subfolders: `identity/` (business-info, voice, audience, strategy, mayank, pang), `sales-and-delivery/` (offer, guarantee, sales-playbook, sales-discovery-call, intake-form, delivery, workflow-build), `playbooks/` (linkedin-playbook, x-playbook, upwork-loom-script, swipe-file). See [shared/context/.overview.md](shared/context/.overview.md) for the full loading discipline by task. CLAUDE.md is for system architecture; `shared/context/` is for brand voice. Don't duplicate identity content into module folders — reference it.


## 13. PRE-BUILD CHECKLIST — DATABASE & EXTERNAL APIs

**See [.claude/checklists/database.md](.claude/checklists/database.md)** for the full pre-build checklist covering Supabase schema, external APIs, and deployment validation.


## 14. DIVINECORE V2 — CODE-FIRST RUNTIME

**See [divinecore-v2/.overview.md](divinecore-v2/.overview.md)** for detailed breakdown of stack (FastAPI + Celery + Redis + Docker Compose), integrations (Fathom, Upwork, Instantly, Apify jobs feed), CI/CD workflow, deployment architecture, and roadmap (auto-deploy + TLS cert pending).


## 15. CLAUDE CODE SLASH COMMANDS

Project-scoped slash commands live in `.claude/commands/` and are version-controlled. Each `.md` file becomes an invocable command (e.g. `prime.md` → `/prime`).

| Command | Purpose |
|---------|---------|
| `/prime` | Load full DivineCore context at session start. Reads `CLAUDE.md` + `README.md`, lists `divinecore-v2/`, runs `git log --oneline -20`, and reads `.claude/session.md` if present. Ends with a briefing on active modules, v2 stack state, and recent commit activity. Use this at the top of any non-trivial session. |
| `/resume` | Lightweight re-entry. Reads `CLAUDE.md` (and `.claude/session.md` if present) and gives a one-paragraph briefing: what was done last session, current state, single next action. |
| `/save-context` | Writes a ≤300-word session summary to `.claude/session.md` covering what changed, current state, decisions made, and the next step to resume from. Note: per commit `13faee3` we now lean on `git log` for progress tracking, so this is optional — use it only when the in-flight state genuinely won't be obvious from commit history. |

When adding new commands, keep them small and composable. One command, one job — same rule as agents.


## 16. TIERED CONTEXT CONVENTION (L0/L1/L2)

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
