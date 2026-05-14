# DivineCore — Business Intelligence Layer
### The Plan

---

## The Problem

Right now, every time we use an AI agent inside DivineCore, we have to manually brief it on what is happening in the business. What we are working on, what stage we are at, what is performing, what is not. This is inefficient and does not scale. As the business grows, this manual feeding becomes a full-time job.

---

## The Vision

Build a system where the business feeds itself into the AI automatically. No manual updates. No briefing. The AI always knows what is going on because it is connected to where the work actually happens.

---

## How the Business Generates Information Today

| Source | What It Contains | Current Status |
|--------|-----------------|----------------|
| Google Meet / Fathom | Team call transcripts, decisions, action items | Already built — Pang's Fathom integration transcribes, categorizes, writes to Supabase |
| WhatsApp | Day-to-day business discussions, sales updates, admin decisions | Not tracked |
| Claude Code | Engineering work, what is being built, commits, session context | Documented via git commits |
| Pulse (Supabase tasks table) | Tasks, deadlines, assignees, status | Live |
| Discord | Agent outputs, team interactions | Partially tracked |

**The gap:** WhatsApp discussions are invisible to the system. They contain the most important business context — what deals are happening, what decisions are being made, what the team is working through — and none of it is captured.

---

## The Fix — Move WhatsApp to Discord

This is the single highest-leverage step. Everything else depends on it.

When the team moves all communications to Discord:
- Every discussion is logged automatically
- Every decision is searchable
- Every update is available to the AI without anyone doing extra work
- The existing Discord infrastructure (bots, channels, middleware) already handles this

Discord channels map cleanly to business departments that already exist — branding, sales, operations, recruitment, pulse. Team discussions go to the right channel and the system knows what context to attach.

---

## The Synthesis Layer — How the AI Stays Updated

Once data flows from all sources into one place, a scheduled job runs nightly and does the following:

1. Reads the last 7 days of data from:
   - Fathom meeting summaries (already in Supabase)
   - Discord channel messages
   - Pulse task statuses
   - Git commit messages

2. Runs a summarization pass — asks Claude to extract the current state of the business into structured format:
   - What are we working on right now
   - What decisions were made this week
   - What is performing, what is not
   - What the team is focused on
   - Any blockers or open questions

3. Saves the output to a `business_context` table in Supabase with a timestamp.

4. AI agents query this when they need business context — always fresh, always current, no manual input required.

---

## The Agent Layer — Cost-Effective Context Injection

Not every agent query needs business context. Injecting it every time wastes tokens and adds cost.

The brain router (already built in IMAGYN) gets extended to return not just a model choice but also which context modules to load:

- "Give me a content idea" → load business context + Kallaway KB
- "What hook works for this topic?" → load Kallaway KB only
- "Quick question about format" → load nothing extra

The AI only loads what it needs for that specific query. As the business context grows, this keeps costs predictable.

---

## The Bigger Picture — A New Kind of Operating Environment

What we are building for DivineCore is not just an internal tool. It is a proof of concept for a new category.

Most businesses run on a mix of WhatsApp groups, Google Docs, spreadsheets, and email. None of it is connected. None of it feeds into any intelligence layer. Decisions disappear into chat threads. Context is lost every time someone new joins or a week passes.

DivineCore proves that a business can run differently:
- One communication environment (Discord)
- Everything logged and structured automatically
- AI agents that always have context and never need briefing
- A brain that grows with the business

When this is proven internally, it becomes the product we sell to clients. Not just an AI OS that runs business functions — but an operating environment where the business feeds the AI and the AI feeds the business back.

The client does not need to manage a knowledge base. They just work. The system learns.

---

## How This Separates From the Market

We researched what already exists. Here is why none of it is doing what we are building:

| Tool | What It Does | Why It Falls Short |
|------|-------------|-------------------|
| Jasper, Writesonic, Copy.ai | Brand voice memory + content generation | Generic output. Requires manual brand setup. No expert framework. No business intelligence layer. You still have to brief it every time. |
| ChatGPT / Claude | General purpose AI | Competent but generic. No brand context. No framework. No connection to what is happening in your business. |
| Jasper IQ | Ingests brand docs as a RAG layer | Closest competitor. But it is a passive document store — you load it once and it sits there. It does not update as your business evolves. No synthesis. No live tracking. |
| VidIQ / TubeBuddy | YouTube analytics and keyword research | Post-publishing optimization only. No ideation. No strategy layer. |
| Palo (ex-MrBeast) | AI ideation + analytics for creators | Early stage. No expert framework evident. No business intelligence layer. Focused on analytics, not strategic ideation. |
| Fathom, Otter, Fireflies | Meeting transcription | Captures meetings but does nothing with the data beyond summaries. No synthesis. No connection to agents. |

**The gap the entire market has missed:**

Every tool treats AI as a content machine you feed inputs into. You write a brief, you upload brand docs, you prompt it. The AI produces output. You evaluate. You repeat.

Nobody has built a system where the business itself becomes the input — where what your team discusses, decides, and builds automatically feeds into the intelligence layer so the AI always knows what is happening without anyone doing extra work.

The reason nobody has built this is because it requires three things working together:
1. A communication infrastructure where all business activity flows through one place
2. A synthesis layer that turns raw activity into structured business context
3. Agents smart enough to know when to use that context and when not to

We are building all three. That is the separation.

---

## Immediate Next Steps

1. **Move team comms from WhatsApp to Discord** — highest leverage, enables everything else
2. **Build the synthesis layer** — nightly job that reads all sources and writes to `business_context` table in Supabase
3. **Extend the brain router** — return context modules alongside model selection
4. **Wire IMAGYN to pull from `business_context`** — agent always knows what DivineSide is doing without being briefed

---

## What This Solves

| Problem | Solution |
|---------|----------|
| Manually briefing agents every session | Synthesis layer keeps context current automatically |
| Business knowledge locked in WhatsApp | Move to Discord — everything tracked |
| Token cost of always injecting context | Brain router only injects context when the query needs it |
| Context becoming stale as business evolves | Nightly synthesis job keeps it fresh |
| Scaling to clients | Same architecture, different data sources — plug in their comms, meetings, tasks |
