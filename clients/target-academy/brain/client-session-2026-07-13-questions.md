# Client Session — 2026-07-13 — Questions to Lock (Phase B: exam-wise generation)

Everything below is a decision only the client can make. Where we have data, the
**measured proposal** from his own real papers is stated — he reacts, we lock.
Capture answers inline; they go straight into `blueprint.py` config + `brain/decisions.md`.

---

## 1. Exam families & paper anatomy

- [ ] **Which exams matter most, in order?** We have PYQ data for: vdo-vpdo,
      lekhpal-patwari, group-c (+ un-ingested: stenographer, driver, junior-assistant,
      livestock-officer). Which 2-3 do we productize first?
- [ ] **Total questions per generated paper, per exam?** (Real papers: 100. Same?)
- [ ] **Per-subject question counts.** Proposal = measured from his real papers:
      | exam | gen-gk | hindi | uk-gs | uk-hist | uk-cult | uk-geo | computer |
      |---|---|---|---|---|---|---|---|
      | vdo-vpdo | 32 | 19 | 12 | 12 | 12 | 10 | 3 |
      | lekhpal-patwari | 38 | 26 | 10 | 10 (geo) | 6 | 6 | 4 |
      | group-c | 40 | 4 | 12 | 20 | 11 | 10 | 3 |
      Confirm/adjust per exam. (Note: his syllabus knowledge > our sample of 7 papers.)
- [ ] **Section order on the paper** — subjects in what sequence? Mixed or sectioned?
- [ ] **Bilingual?** Real papers are English-left/Hindi-right. Generated papers are
      currently Hindi-only. Is Hindi-only acceptable for practice papers, or is the
      English column required? (English column = meaningful extra work — flag effort.)

## 2. Question formats (MCQ types)

**THE MENU — show him this table, he ticks + gives a % for each.** (Researched
against UPSC/SSC/state-exam taxonomies so nothing is a blank "what are they?".
Note: UPSC introduced type 4 in 2022 specifically to defeat option-elimination —
the same philosophy as his "confusing, not obvious" rule.)

| # | Format (Hindi = English) | What it looks like | In his PYQs | Our status |
|---|---|---|---|---|
| 1 | सीधा प्रश्न = **Single correct / direct** | One fact, 4 options: "X के सम्पादक कौन थे?" | 87.5% | ✅ ready |
| 2 | सुमेलित / मिलान = **Match the Following** | सूची-I ↔ सूची-II + कूट (code) options | 8.9% | ✅ ready |
| 3 | कथन-आधारित = **Multiple statements — which is/are correct** | "निम्न कथनों पर विचार कीजिए… कौन-सा/से सही है/हैं?" → "केवल 1 और 2" | 1.9% | ✅ ready |
| 4 | उपर्युक्त में से कितने सही = **"How many of the above are correct?"** | Same statements, but options = "केवल एक/दो/तीन/सभी" — kills elimination (UPSC 2022+ trend) | rare | 🔶 30-min add (variant of #3) |
| 5 | अभिकथन-कारण = **Assertion–Reason (A/R)** | कथन (A) + कारण (R) → 4 canonical options: both true & R explains A… | 0.5% | ✅ ready |
| 6 | कथन-I/कथन-II = **Statement-I & Statement-II** | Newer UPSC A/R variant: two statements, does II explain I? | rare | 🔶 30-min add (variant of #5) |
| 7 | सही क्रम / कालक्रम = **Chronological / sequence ordering** | "निम्न को कालक्रमानुसार व्यवस्थित कीजिए" → code options | 0.7% | ✅ ready |
| 8 | सत्य/असत्य = **True / False** | "निम्न में से सत्य कथन चुनिए" (or a T/F pair grid) | ? (his whiteboard mention) | 🔶 needs his example first |
| 9 | सही सुमेलित युग्म = **Which pairs are correctly matched** | 3-4 pairs listed inline → "कौन-सा/से युग्म सही सुमेलित है/हैं?" — match×statement hybrid, common in state exams | present in sources | 🔶 1-hr add |
| 10 | निषेधात्मक = **Negative ("which is NOT…")** | "कौन-सा सही सुमेलित **नहीं** है?" / "…नहीं है?" | present | 🔶 trivial add (plain variant) |
| 11 | विषम = **Odd one out** | "निम्न में से कौन भिन्न है?" | present | 🔶 trivial add |
| 12 | रिक्त स्थान = **Fill in the blank** | Mostly in the Hindi-grammar section | present (hindi) | 🔶 trivial add |
| 13 | अवधारणा-अनुप्रयोग = **Concept application / scenario** | A situation described → apply a concept (analytical, UPSC-style) | rare in UKSSSC | ⬜ later, if wanted |
| — | आकृति-आधारित = **Figure/diagram-based** | Reasoning figures | ~0.4% | ❌ can't generate diagrams |

- [ ] **Which formats does he want, at what % each?** (per exam if they differ).
      Measured baseline from his real papers: #1 87.5%, #2 8.9%, #3 1.9%, #7 0.7%,
      #5 0.5%. Keep realistic, or boost complex formats for practice intensity?
- [ ] **True/False (#8)** — get ONE example from his papers of what it looks like,
      then we build the contract same-day.
- [ ] **सुमेलित (Match) category preferences** — which pair-kinds does he rate
      highest (author↔work / लेखक↔रचना, temple↔district / मंदिर↔जिला,
      event↔year / घटना↔वर्ष, scheme↔year / योजना↔वर्ष…)? Any he avoids?
- [ ] **Difficulty mix** — easy/medium/hard shares? And HIS definition of hard
      (obscure fact? multi-step? close distractors?). Currently prompt-level only.

## 3. The quality bar — gold questions (the big ask)

- [ ] **~15 gold-standard questions per complex format** (Match the Following,
      statement-based, Assertion–Reason, ordering + true/false if added) — picked
      from his own bank or written fresh. These become the style examples the AI
      imitates; his taste becomes the target. Format: plain list, each ending
      `Answer – (X)` — ingests as-is.
- [ ] **Distractor rules beyond "confusing, not eliminable"** (already enforced) —
      any other rules he applies when writing options? (e.g. "उपर्युक्त में से कोई
      नहीं" = "none of the above" — allowed as an option? allowed as the CORRECT
      answer? how often?)
- [ ] **Review the 12-question sample docx WITH him** — line by line. Capture every
      objection verbatim → each becomes a rule (mechanical if possible, prompt if not).

## 4. Corpus (books)

- [ ] **Per-subject book trust ranking** — which books does he consider authoritative
      per subject? (Retrieval can weight them.) Any book in our list he DISTRUSTS?
      Current: 22 books, 6+1 subjects; strongest gen-gk/history; thinnest uk-geography
      (2 books), uk-culture depth (fairs/festivals/instruments), uk-general-studies.
- [ ] **Books to add** — his recommendations for the thin subjects above (evergreen
      reference books only — current affairs stays OUT per Mayank's rule).
- [ ] **Computer subject depth** — Lucent computer book enough, or add one more?
- [ ] **Current affairs handling** — corpus excludes it (goes stale). How does HE want
      CA questions in practice papers: he supplies them manually per paper? A separate
      section we leave blank? Skip entirely?

## 5. PYQ corpus (style bank)

- [ ] **Which exams' past papers to add next?** The junior-assistant solved-papers
      compilation (in corpus, un-ingested) — worth ₹? More UKSSSC papers from
      ExamPillar? His own institute's paper archive??  ← that last one could be gold.
- [ ] **His own past papers** — does the institute have its own authored papers
      (the "questions we make")? Those are the ultimate style bank — better than
      commission PYQs for style. Can we get them as PDFs/docs?

## 6. Workflow & delivery

- [ ] **Who operates generation** — owner? Aryan? What review happens before a
      generated paper reaches a class? (Solution doc flags exist for this.)
- [ ] **Feedback loop** — when a teacher spots a bad generated question, where does
      it go? (Proposal: a note per question # → we add each to decisions.md and turn
      systematic ones into rules.)
- [ ] **Volume expectation** — papers per week per exam? (Determines whether ~15 min
      per 100-q paper is comfortable and what the monthly API budget looks like: ~₹85
      /100-q paper at current rates.)
- [ ] **Deliverable set for generated papers** — same trio as extraction (class PPT +
      teacher solution + branded paper + answer key)? Solutions: does he want the
      विस्तृत व्याख्या (= detailed explanation) style for every generated question?

## 7. Housekeeping (2 min)

- [ ] **Sarvam credits** — ~₹520 more finishes the re-OCR queue (2 damaged history
      books, हरदेव बाहरी grammar, 2 scanned notes, UKCurrent) + ₹75 for the 8 PYQ
      PDFs. More fresh accounts today, or a paid top-up on one?
- [ ] **Damaged-book replacements** — the 2 remaining digit-corrupted history books
      re-OCR when credits land; okay that uk-history generation runs on the other
      3 books until then? (Quality currently fine — BAHI302 carries the depth.)
