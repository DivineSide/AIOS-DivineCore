# UKSSSC Official Syllabus Reference — 2026-07-18

Primary-source syllabus research for the exam-mode generation layer. Everything
here was read from the commission's own advertisement PDFs (sourced from
sssc.uk.gov.in → cdnbbsr.s3waas.gov.in), NOT aggregator sites. The PDFs are
archived locally (gitignored, like books) in `corpus/syllabus-official/`.

## The one finding that shapes the architecture

**UKSSSC uses ONE master syllabus across its general written exams.** The
Group C graduate-level paper (Advt 70/2025) and the Police Constable paper
(Advt 65/2024) carry word-for-word identical परिशिष्ट-1 syllabi — same three
parts, same topic lists, same author lists, same 20/40/40 marks split.
Verified page-by-page, both documents. Genuinely different syllabi exist only
for specialist posts (see per-exam table).

Consequence: the exam-mode topic layer needs ONE taxonomy config
(`DsideOS/worker/syllabus.py`), not one per exam name. The client's exam
dropdown can grow to any master-syllabus exam family with a blueprint
SUBJECT_MIX entry and zero new syllabus work.

## The master syllabus (100 marks)

| Part | Subject | Marks | Maps to corpus subject(s) |
|---|---|---|---|
| भाग-1 | सामान्य हिंदी (भाषा एवं साहित्य) — 13 items incl. संधि/विलोम/वाक्य-शुद्धि grammar + named पद्य/गद्य साहित्यकार | 20 | `hindi` |
| भाग-2 (क) | मानसिक योग्यता एवं तर्कशक्ति — 29 verbal + 12 non-verbal topic list | (inside 40) | — NOT generatable (reasoning-mode parked) |
| भाग-2 (ख–च) | इतिहास, भूगोल, राजनीति विज्ञान, अर्थशास्त्र, समसामयिक (भारत एवं विश्व) | (inside 40) | `general-gk` |
| भाग-2 | Fundamentals of Computers — 5 units | (inside 40) | `computer` |
| भाग-3 | उत्तराखण्ड से संबंधित विविध जानकारियाँ — 13 items | 40 | `uk-history`, `uk-geography`, `uk-culture`, `uk-general-studies` |

The full topic-level transcription (decomposed to question-sized granularity)
lives in code: `DsideOS/worker/syllabus.py` — that file is the operational
copy; this doc is the provenance record.

## Per-exam status

| Exam / post family | Syllabus | Status |
|---|---|---|
| Group C graduate level: Patwari, Lekhpal, VDO, VPDO, ARO, Personal Assistant, Assistant Superintendent, Swagati (Advt 70/2025, 09-Apr-2025, 416 posts) | Master syllabus | ✅ VERIFIED (primary PDF, 41 pp) |
| आरक्षी जनपदीय पुलिस + PAC/IRB (Advt 65/2024, 30-Oct-2024, 2000 posts) | Master syllabus — identical | ✅ VERIFIED (primary PDF, 28 pp) |
| Van Aarakshi, Sachivalaya Rakshak, Aabkari Sipahi, Kanishtha Sahayak (inter-level family) | Master syllabus (predicted) | 🔶 HIGH-CONFIDENCE PREDICTION — same commission conventions, general-post type; spot-verify one before load-bearing use |
| Driver / प्रवर्तन चालक (Advt 10-Apr-2026) | 25-mark written (वाहन चालन + सामान्य ज्ञान) + 75-mark driving test | ✅ VERIFIED — thin by design, low value for paper generation |
| Livestock Extension Officer (Advt 76/2026, 08-May-2026) | Specialist: भाग-A common + भाग-B (जीव विज्ञान) / भाग-C (कृषि+पशुपालन) elective; degree-level English content | ✅ VERIFIED — entirely outside current corpus; own build if ever wanted |
| Assistant Teacher (LT) | Subject-specific (per teaching subject) | ❌ not sourced — left per Mayank (low value) |
| Stenographer skill-test component | Typing/shorthand qualifying test on top of written paper | ❌ not sourced — written part is covered by Group C |
| EO (Executive Officer) | — | ❌ never located; possibly not UKSSSC |

## Archived PDFs (`corpus/syllabus-official/`, local-only)

- `advt-70-2025-groupc-graduate-level-patwari-vdo-aro.pdf` — the master
  syllabus source. परिशिष्ट-1 starts p24 (भाग-1 हिंदी, अंक-20), p25 (भाग-2
  तर्कशक्ति, अंक-40 header), p26 (computers), p27-28 (इतिहास, भूगोल), p29-31
  (राजनीति विज्ञान), p32 (अर्थशास्त्र, समसामयिक), p33 (भाग-3 उत्तराखण्ड,
  अंक-40). p34+ are administrative annexures.
- `advt-65-2024-police-constable-pac-irb.pdf` — परिशिष्ट-1 from p18; verified
  identical to the above.
- `advt-2026-driver-pravartan-chalak.pdf` — परिशिष्ट-1 at p18: 25Q written +
  driving test.
- `advt-76-2026-livestock-extension-officer.pdf` — specialist biology/agri
  syllabus, 42 pp.

## How this feeds generation (wired 2026-07-18)

- `worker/syllabus.py` — official taxonomy per corpus subject +
  `MASTER_SYLLABUS_EXAMS` + `topics_for(subject, exam)`.
- `worker/generate.py` — `_extract_topics(subject, count, exam=None)`: exam
  mode samples topics from the official taxonomy (PYQ inference only as
  top-up / subject-mode fallback). `generate_exam` passes exam through.
- `worker/blueprint.py` — `police-constable` added to SUBJECT_MIX: part-level
  weights official (20/40/40), within-part sub-splits derived from group-c
  measured ratios until his constable papers land in pyq_chunks.
- `worker/tasks.py` + `api/main.py` — `/api/generate` accepts `exam`;
  meta.exam routes the Celery task to `generate_exam`.
- Per-topic PYQ style lookup is unchanged — and a syllabus topic with zero
  PYQ coverage still generates (style prompt degrades to "standard UKSSSC
  framing"), which is the freshness win: a syllabus revision is coverable
  the day the commission publishes it, years before PYQs exist for it.

## Open threads

- Within-भाग-2 sub-split (history vs geo vs polity vs econ vs current) is not
  officially specified — measured SUBJECT_MIX remains the authority there.
- तर्कशक्ति share of भाग-2 is officially real but ungeneratable until the
  reasoning-mode design ships; its weight is folded into general-gk.
- Client conversation still owns: final per-exam mixes (GEN_SUBJECT_MIX_*
  overrides), and whether inter-level exams (Van Aarakshi etc.) get their own
  blueprint families (needs one syllabus spot-check + measured papers).
