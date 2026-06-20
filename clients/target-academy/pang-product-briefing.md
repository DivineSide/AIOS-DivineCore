# What We've Built — Product Briefing for Pang

> Pang — you said you can't pitch something you don't understand, and you're right. This
> is the whole thing in one read: what the product *is*, what we've actually built and
> tested, how it works under the hood, and why it travels to the US/UK. Written so you can
> walk into a call and explain it without me on the line.

---

## 1. The one-sentence version

**We turn a coaching institute's manual content grind into a machine.** The owner's team
spends ~2 hours making one class PPT by hand — typing questions, formatting, building the
deck. We replaced that with a system: questions in → finished, branded, print-ready class
material out in minutes, in *their exact template, their font, their branding*.

That's the pitch. Not "AI", not "automation tool" — **"the typing-and-formatting work your
team does, done by a system, in your format, in minutes."**

---

## 2. The client — Target Academy (who this was built for)

- **Target Academy** — 8-year coaching institute in India, govt-exam prep (UKSSSC — Patwari, Lekhpal, VDO, etc.).
- Owner's **#1 named pain, unprompted:** making study content. "2 hours per PPT" + a separate
  person for approval, then it's read in the online class and sent to students as PDF via
  Telegram / their app / WhatsApp.
- He's **already sold** — saw the demo and said *"anybody will buy this — you're my first
  customer for sure."* He has **50+ connections** in the same business = our distribution.
- Skeptical of AI ("maybe AI will make mistakes") — which is why the system has a built-in
  verification + human-check gate (see §5). That skepticism is universal; the gate is our answer.

---

## 3. What we've actually built (working, tested — not slideware)

Three deliverables come out of one input, all in **his real template** (we use his actual
files as the base, so borders/watermark/branding are inherited, not imitated):

| Deliverable | What it is | Shown to students? |
|---|---|---|
| **In-class PPT** | The question paper as slides — verbatim MCQs, **no answers** | ✅ shown live in class |
| **Teacher solution doc** | Every answer + a one-line reason; full worked steps for maths/reasoning | ❌ teacher only |
| **Branded practice paper** | Full Word paper in his format + answer key page (उत्तरमाला) | ✅ exported to PDF, sent to students |

Plus a **marketing poster** generator (batch/course posters in his style) — the second
workflow he's pulling for.

**Proven on a real exam paper:** we ran the full pipeline on an actual UKSSSC Patwari paper
(100 questions, Hindi) end-to-end. All three files generated clean. We also stress-tested the
live path (a brand-new exam paper photographed → read → generated) and the garbage-input
cases. It holds.

---

## 4. How it works under the hood (for you as the dev)

The key insight: **almost none of this is AI.** That's what makes it fast and cheap.

```
   exam paper / topic                         [AI layer — small, surgical]
        │                                      • read an image-PDF (vision)
        ▼                                      • figure out + verify answers
   questions JSON  ◄──── the only AI step ────┤• write the one-line reasons
        │                                      └─ generate original questions from PYQs
        ▼                                      
   run_pipeline.py  ─── pure Python, $0, instant ───►  PPT + Solution + Paper
   (python-pptx / python-docx)
```

- **The three generators are pure Python** (`build_deck.py`, `build_solution.py`,
  `build_paper.py`). Zero API calls. A 100-question paper costs **₹0** to format.
- **The only metered cost is the AI layer** — reading a paper and reasoning out answers.
  Roughly **$0.15–0.20 per 100-question paper** on the Anthropic API.
- **One hard technical problem solved:** the institute uses **Kruti Dev 010**, a legacy
  non-Unicode Hindi font (glyphs mapped onto ASCII). We built a bidirectional
  Unicode↔KrutiDev converter (`krutidev.py`) so we can both read their existing files and
  write output in the exact font their decks use. This is a real moat detail — generic AI
  tools output Unicode and render as garbage in their template.
- **Orchestration:** `run_pipeline.py` is a single entry point with a **hard input gate** —
  it refuses to run unless exactly one valid questions file is staged. One command → all
  three artifacts. This is the `/run-pipeline` skill.

---

## 5. The trust gate (this is the sales answer to "AI makes mistakes")

When the paper is brand-new (no official answer key out yet), we don't just trust the model:

- Every answer is **confirmed against two reliable sources** (ExamPillar + Testbook first).
- Both agree → ships, marked confirmed (green ✔ in the teacher doc).
- Only one source / they disagree / it's a tricky one → **flagged RED** for Mayank's manual
  check before anything reaches the class.
- Maths/reasoning answers carry a full worked solution → self-verifying.
- **The flags live in the teacher doc only — never on the branded student-facing material.**

So the line for a skeptical owner is: *"every answer is double-confirmed, and your final-check
step stays exactly as it is."* The machine does the labor; the human still supervises.

---

## 6. Current status & what we are NOT doing yet (important — don't over-promise)

- **Everything is manual right now, on purpose.** Mayank runs it from his machine. **No UI,
  no hosting, no deployment.** This is a deliberate decision: one week of real production
  testing on the live client before we lock in a UI and authorization layer. Don't pitch a
  dashboard or a self-serve app — it doesn't exist yet and that's strategic, not a gap.
- **No pricing numbers** in any conversation. When pricing comes up: "compared to what you
  already spend on content — staff time, effort." Never quote a figure.
- The next workflow after content is the **marketing engine** (results/testimonials/referrals)
  — the owner is pulling for it.

---

## 7. Why this sells abroad (the US/UK angle Mayank raised)

The deep-research takeaway: **education/coaching businesses exist worldwide, and they all run
on content.** Every country's exams, formats, and branding differ — so the *delivery shape*
changes (a US test-prep company's worksheet ≠ a UKSSSC PPT). **But the engine is the same:**
take a business's content need, generate it in *their* format and branding, fast and cheap.

That's the reusability: we're not selling "Indian exam PPTs." We're selling **a content engine
that adapts to any education business's format.** India is where we're proving it because we
have a warm client and fast access. The US/UK is where the same engine earns 5–10x the pricing
power. The format layer is configurable; the core (questions/content → branded, verified output)
is universal.

**So when you talk to foreign prospects:** the differences between countries don't weaken the
offer — they're why a *custom* content engine beats a generic template tool. Every market needs
its own format, and that's exactly what this does.

---

## 8. How to pitch it on a call (your cheat sheet)

1. **Lead with the pain, not the tech:** "How much time does your team spend making study
   material / worksheets / question sets every week?" Let them say the number.
2. **The promise:** "We make a system that produces all of that — in your exact format, your
   branding — in minutes instead of hours. Your team's job shifts from making it to checking it."
3. **The trust line:** "Every answer is double-verified, and your review step stays exactly as
   it is. The machine does the typing; your people still approve."
4. **Proof:** we have a live client in India using it, and we can show finished sample output.
5. **Do NOT:** quote a price, promise a dashboard/app, say "AI" as the headline, or claim it's
   fully automated. It's a *system that does the work, supervised by a human.*

If they want to see it: tell them we'll send sample output (the PPT + paper + solution set).
Ask Mayank for the latest clean samples before the call.

---

*Questions → ask Mayank. The codebase lives in `clients/target-academy/`; the pipeline is
`pipeline/run_pipeline.py` behind the `/run-pipeline` skill.*
