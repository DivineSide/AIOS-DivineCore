# Workflow Build — DivineSide

> **IN REVIEW until 2026-06-05.** This is Phase 3 of the **destination** 8-week pilot ([`delivery.md`](delivery.md)). The engineering-side guidance (n8n vs divinecore-v2 decision, 6-step build flow, where things commit) **remains live and applies to current Phase 1 custom builds.** What's destination-specific and in review: the strict 2-week timing, the prereq that requires a validated 8-category brain (current Phase 1 builds may use a tighter context surface), and the framing as "the pilot workflow build" rather than "a custom workflow build." Treat engineering content as live; treat pilot-framing as in-review. See [`../../../CLAUDE.md` §2](../../../CLAUDE.md) for the Phase 1/2/3 arc.

> **The internal SOP for building a pilot workflow** — Phase 3 of [`delivery.md`](delivery.md). What to check before starting, where the code lives, how to ship.
>
> Starter doc. Grows with each pilot — patterns become templates after 3-5 builds.
>
> **Notion mirror:** *[paste link here after uploading to Notion]*
>
> **Loading discipline:**
> 1. [`delivery.md`](delivery.md) — the broader pilot flow this fits into
> 2. [`offer.md`](offer.md) — what we promised (one workflow, ≤2 weeks build, measurable in hours saved)
> 3. **This file** — how the workflow gets built

Last updated: 2026-05-04

---

## 01 · Before you start (prereq check)

Don't start a workflow build until all three are true:

- [ ] **All required API keys live** (per the tech access checklist in [`delivery.md`](delivery.md) §09). Don't build against mocked data — fix access first.
- [ ] **The 8-category brain is built and validated** (per [`delivery.md`](delivery.md) §05). The workflow queries the brain. Half-done brain → half-grounded workflow.
- [ ] **Workflow scope written down** in 2-3 sentences with a measurable success criterion. If you can't write the scope cleanly, you can't build it cleanly.

If any of these are false, go back. Don't paper over.

---

## 02 · Where the workflow lives — n8n or divinecore-v2

Two homes available:

| | n8n | divinecore-v2 |
|---|---|---|
| **Hosted at** | `n8n.srv1445995.hstgr.cloud` (Hostinger VPS) | `/root/divinecore-v2/` on the VPS |
| **Best for** | Glue between SaaS APIs (Shopify ↔ Klaviyo ↔ Slack), simple triggers, anything that fits a node-graph cleanly | Anything LLM-heavy, custom logic, agentic flows, anything that gets unwieldy as a node graph |
| **Speed to build** | Fast for simple flows | Slower upfront, faster to iterate later |
| **Maintainability** | Node graphs get brittle past ~30 nodes | Code is reviewable, testable, version-controlled |

**Default rule:** if the workflow fits as a clean n8n graph in ≤20 nodes, build it in n8n. If it needs LLMs in the loop, agentic decisions, or branching beyond what fits a graph, build it in divinecore-v2 Python.

When in doubt, lean divinecore-v2 — it's the long-term direction (CLAUDE.md §13).

---

## 03 · The build flow (~2 weeks)

Same shape regardless of where it lives:

1. **Spec (day 1)** — write the workflow spec in the client's brain repo: what it does, what it doesn't, inputs, outputs, success metric, edge cases. Commit to `<brand>-ai-brain`.
2. **Build (days 2-7)** — implement.
3. **Internal test (days 8-9)** — run with synthetic data, then with a sample of real client data. Confirm the hours-saved math is plausible against the baseline log.
4. **Client preview (day 10)** — short demo to the founder or function owner. Get sign-off before going live.
5. **Ship live (day 11)** — deployed, monitoring on, team walkthrough done.
6. **Monitor + tune (days 12-14)** — watch closely for the first 3-5 days, fix anything breaking, capture issues for the brain's `decisions.md`.

---

## 04 · Where things commit

- **Workflow spec + handoff docs** → client's brain repo (`<brand>-ai-brain` on GitHub)
- **n8n workflow JSON exports** → relevant module folder (`branding_os/workflows/`, `sales_os/workflows/`, etc.) per CLAUDE.md §11
- **divinecore-v2 Python code** → `<module>/integrations/<feature>/` (e.g. `sales_os/integrations/upwork/`, `ops_os/integrations/fathom/`); divinecore-v2/ stays runtime-only
- **Credentials** → Bitwarden vault. Never in code, never in git.
- **Run logs / metrics** → TBD; flag if you build a monitoring layer

---

## 05 · What this doc is, what it isn't

**It is:**
- The starter SOP for the first 5 pilot workflow builds
- A doc that grows with each pilot — patterns become templates after 3-5

**It isn't:**
- Per-workflow templates yet (those emerge from real builds, not pre-imagined ones)
- A code style guide — write that separately when there's enough code to style

**Update cadence:** append a one-liner to `## 06 · Lessons` after every workflow ship.

---

## 06 · Lessons

*(One-liner per workflow shipped — n8n or divinecore-v2, how long it actually took, what broke in week 1, what the hours-saved number landed at, what surprised us.)*
