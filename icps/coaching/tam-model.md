# TAM Model — DSideOS (RAG Question-Paper Generator)

**Last updated:** 2026-07-23 · **Status:** first-pass estimate, refreshable
**Product being sized:** the RAG engine that generates *original* exam question
papers grounded in real source books + real previous-year-paper (PYQ) patterns,
calibrated to a specific exam's official syllabus. (Format rendering / PPTs are
packaging around this engine — not the thing being sized.)

> **Framing that matters.** The published "test-prep market" / "tutoring market"
> numbers ($7.2B India coaching, $70B global tutoring, etc.) are the WRONG TAM
> for us. Those size *student spend on instruction*. We don't sell instruction —
> we sell **question-paper production** to the *supply side*. Our TAM is:
>
> **(count of institutions that produce or sell question papers) × (annual price they'd pay for grounded generation)**
>
> This is a "picks and shovels" TAM, not a slice of the tutoring market. It is
> smaller in headline dollars but far more targetable for a new startup.

---

## 1. The buyer universe (who produces/sells question papers)

Anyone who sells or produces question papers is a valid buyer. Ranked by how
targetable they are for a **new startup with no brand** (your explicit filter):

| Tier | Buyer | Targetable now? | Why |
|------|-------|-----------------|-----|
| **A — beachhead** | Coaching institutes (small/mid, exam-prep) | ✅ **YES** | Produce practice papers weekly by hand (~2h/paper). Warm network (Target Academy + 50 intros). Owner-decision, short sales cycle, low switching cost. **Start here.** |
| **B — near-term** | Independent tutors / small tuition centres | ✅ yes (volume play) | Same pain, smaller budget. Only viable via self-serve/low-touch. |
| **B — near-term** | Small/regional exam-book publishers & question-bank sellers | 🟡 partial | Produce papers at scale = high value per account, but longer sales cycle, quality bar high. Good *second* segment. |
| **C — later** | Schools / colleges (internal exams, assessments) | 🟡 later | Institutional procurement, slow, need trust. Big but not startup-friendly day 1. |
| **D — not yet** | Large EdTech / test-prep platforms (Testbook, PW, Adda247, Byju's) | ❌ **no** | They build in-house or buy from established vendors. No brand = no entry. Revisit post-traction. |

**Startup-reachable buyer = Tier A + B.** That's the SAM you actually chase.

---

## 2. India — the prototype ground

### Anchor counts (sourced)
- **~68,181 coaching centres** in India (Oct 2025, business-listing scrape).
  Top states: UP 11,144 · Maharashtra 8,961 · Bihar 6,383. [rentechdigital]
- India coaching-institutes market: **~$7.2B (2025)**, ~10% CAGR. [IMARC]
- India test-prep market: **$300M–$11.6B (2025)** depending on definition —
  huge spread = treat as unreliable; use the *center count*, not the $ market. [IMARC / Technavio]
- **7.1 crore (71M) students** enrolled in coaching nationally. [industry press]
- Hundreds of exam-book publishers (Arihant 3,000+ titles, Oswaal, Kiran,
  Lucent, Disha…). Arihant alone is #1 in competitive/recruitment/entrance books.

### India TAM/SAM/SOM (question-paper generation spend)

*Assumption set (flagged — refine with real pricing):*
- Not all 68k centres produce their own papers; the govt-exam / competitive
  segment does most heavily. Estimate **~40% (~27k centres)** are paper-producers
  that would value generation. (⚠ assumption — validate.)
- Blended annual willingness-to-pay, India: **₹30k–₹90k/yr** (~$360–$1,080),
  anchored to the content-team labour cost DSideOS replaces (~2h/paper × cadence).
  Target Academy discovery said price ≈ his current content-staff spend.

| Layer | India | Basis |
|-------|-------|-------|
| **TAM** (all 68k centres × mid price ~₹60k) | **~₹410 cr (~$49M/yr)** | If every centre bought at mid price. Ceiling. |
| **SAM** (27k paper-producers × ₹60k) | **~₹160 cr (~$19M/yr)** | Centres that actually produce papers. |
| **SOM** (realistic 3-yr, ~1–3% of SAM) | **~₹1.6–5 cr (~$190k–$580k/yr)** | 250–800 accounts. First-startup reachable via warm network + regional outreach. |

Add publishers (Tier B): a *few hundred* serious competitive-exam publishers,
higher price per account ($5k–$50k/yr) — small count, large per-logo value.
Rough India publisher TAM **~$10–30M/yr** but slower to land.

---

## 3. Foreign markets (higher pricing power, brand TBD)

### United States
- **~176,000 businesses** in Tutoring & Driving Schools (NAICS 61169), industry
  revenue **~$18.9B (2025)**. Exam-prep+tutoring (611691) is the bulk. [IBISWorld]
- **~19,881 online-tutoring businesses.** [IBISWorld]
- **~21M learners/yr** in standardized testing (SAT/ACT/GRE/GMAT/LSAT/AP/K-12);
  ~2M+ register for the big standardized tests annually. [business-research]
- Pricing power **5–10× India**: plausible WTP **$3k–$15k/yr** per centre.

*US SAM (paper-producing test-prep centres):* if even **~30k** US
establishments produce their own practice material and **~$5k/yr** blended:
**SAM ≈ $150M/yr.** SOM at 1% ≈ **$1.5M/yr** (300 accounts). Far larger dollar
pool than India per logo — but zero warm network and higher trust bar.

### United Kingdom
- Structural, non-cyclical GCSE / A-Level / 11+ demand; **hundreds** of tutoring
  agencies; consolidation underway (IXL acquired MyTutor, May 2025). [imarc]
- Smaller absolute count than US/India; premium pricing similar to US.
- *UK SAM (rough):* thousands of exam-focused agencies × ~£3k–£8k/yr →
  **~$30–80M/yr** order of magnitude. SOM 1% ≈ **$300–800k/yr.**

### Global rollup (test-prep + tutoring)
- Global exam-prep & tutoring: **~$70.7B (2025) → $74.2B (2026)**, ~4.9% CAGR.
  [thebusinessresearchcompany] — again, that's *instruction spend*, our ceiling
  reference only.

---

## 4. Headline first-pass TAM (the numbers to quote)

| Market | Startup-reachable **SAM** (paper-producers) | 3-yr **SOM** (1–3%) | Notes |
|--------|--------------------------------------------|---------------------|-------|
| **India coaching** | **~$19M/yr** | **$190k–580k/yr** | Warm network = fastest path. START HERE. |
| India publishers | ~$10–30M/yr | slower | Second segment, high per-logo. |
| **US test-prep** | **~$150M/yr** | **~$1.5M/yr** | 5–10× pricing power, no brand yet. |
| **UK exam prep** | **~$30–80M/yr** | **~$300–800k/yr** | Premium, consolidating. |
| **Combined SAM** | **~$210–280M/yr** | — | Institutions that produce/sell papers, all geos. |

**One-line pitch-deck version:**
> "The engine addresses institutions that produce their own exam papers. That's a
> **~$200–280M/yr** serviceable market across India, US and UK. We start with
> India coaching (~$19M SAM, warm distribution) and expand to the 5–10× pricing
> power of the US/UK."

---

## 5. Confidence & what to refine

**Low-confidence inputs (fix these first):**
1. **Pricing** — every $ figure hangs on WTP guesses. One real signed retainer
   replaces all of it. (Target Academy retainer will set the India anchor.)
2. **% of centres that produce papers** — the 40% India / ~17% US filters are
   assumptions. A survey of 20 institutes would tighten this hugely.
3. **Publisher count & spend** — only anecdotally sized here.
4. India test-prep $ market spread ($0.3B vs $11.6B) is unusable — ignore it,
   trust the **center count (68k)** instead.

**High-confidence inputs:** institution counts (68k India centres, 176k US
tutoring businesses, 21M US standardized-test learners) — these are the solid
skeleton. The TAM is count-driven, not market-report-driven, on purpose.

---

## Sources
- India coaching market $7.2B / 10.3% CAGR — [IMARC](https://www.imarcgroup.com/india-coaching-institutes-market)
- India 68,181 coaching centres (state breakdown) — [RentechDigital](https://rentechdigital.com/smartscraper/business-report-details/list-of-coaching-centers-in-india)
- India test-prep market (wide spread) — [IMARC](https://www.imarcgroup.com/india-test-preparation-market) / [Technavio](https://www.technavio.com/report/test-preparation-marketin-india-industry-size-analysis)
- India publishers (Arihant/Oswaal) — [Ashirwad Publication](https://www.ashirwadpublication.com/top-publishers-for-competitive-exams-in-india)
- US tutoring 176k businesses / $18.9B / 21M learners — [IBISWorld](https://www.ibisworld.com/united-states/market-research-reports/tutoring-driving-schools-industry/) / [IBISWorld online tutoring](https://www.ibisworld.com/industry-statistics/number-of-businesses/online-tutoring-services-united-states/)
- Global exam-prep & tutoring $70.7B — [The Business Research Company](https://www.thebusinessresearchcompany.com/report/exam-preparation-and-tutoring-global-market-report)
- UK private tutoring / MyTutor acquisition — [IMARC](https://www.imarcgroup.com/private-tutoring-market)
