# LLM calls during a single generate-questions run
1. Topic extraction — _extract_topics() in generate.py:518-579

Calls _complete() → routes via GEN_PROVIDER (Sarvam-105b in prod)
One call per generation run (not per question) — only fires when the official syllabus doesn't already cover the needed topic count
Input: ~40 random real PYQs for the subject; output: a JSON array of distinct topic strings
This is the step that hit the 402 error earlier
2. Query embedding — _embed() in rag/query.py:119-129

OpenAI text-embedding-3-small (or local E5 if EMBED_PROVIDER=e5) — not a generative call, just a vector
Fires twice per slot (once for passage_lookup, once for pyq_rag_lookup) — so ~40 calls for a 20-question paper
Not billed like a chat completion — embeddings are cheap, near-negligible cost
3. HyDE query rewrite — _hyde_expand() in rag/query.py:395-407 (only if RAG_HYDE=1, which is on by default per your .env.example)

gpt-5.4-nano — turns the topic into a hypothetical answer sentence before embedding
Fires once per slot's passage lookup — so once per question
4. Drafting — _draft() → _draft_sarvam() in generate.py:311-333

This is the main event. Sarvam-105b, reasoning disabled, takes the retrieved passages + PYQ style examples + format contract, returns the question's facts as JSON
Fires once per slot (once per question), plus up to 2 retries if validation/grounding rejects it (retry loop in the slot engine, generate.py:830-945)
5. Grounding gate — check() in ground.py:172-203

Claude Haiku 4.5 (or gpt-5.4-nano if GROUND_PROVIDER=openai) — deliberately a different model than the drafter, so it can't rubber-stamp its own mistake
Fires once per drafted question (and again on each retry) — checks whether the claimed fact is verbatim-quotable from the source passages
So for a 20-question paper with zero retries: 1 topic-extraction call + ~20 embedding pairs + ~20 HyDE calls + 20 draft calls + 20 grounding calls — 5 distinct LLM touchpoints, 3 different models/providers (Sarvam for drafting/topics, OpenAI nano for HyDE, Anthropic Haiku for grounding), by deliberate design so no single model both writes and checks its own work.

# LLM/embedding call sites during question generation — complete case list

Two entry modes, different topic sourcing
Subject mode — generate_questions(subject, count)	Exam mode — generate_exam(exam, total)
When used	No exam context (ad-hoc paper for one subject)	Full exam paper — blueprint.subject_mix() splits total across subjects (e.g. 100 → 7 subjects)
Topic source	Random 40-PYQ sample → LLM infers topics	Official syllabus (syllabus.py) first; PYQ-inference only tops up the shortfall

## Case 1 — Topic sourcing (fires once per subject, not per question)
Syllabus exists AND covers enough topics (len(official) >= n_topics, only possible in exam mode, only for the 4 MASTER_SYLLABUS_EXAMS): zero LLM calls. Topics are random.sample() from the static Python list in syllabus.py. This is the case you asked about — the syllabus firing means the LLM-inference branch is skipped entirely, not just deprioritized.
Syllabus exists but is short (fewer official topics than needed): official topics all kept, LLM inference (_complete(), 1 call) tops up the remainder.
Syllabus doesn't cover this subject at all (subject mode always; exam mode for subjects like hindi/computer/general-gk that aren't in MASTER_SYLLABUS_EXAMS's wired topic map, or any exam not in that set): rag.pyq_lookup() (DB query, no LLM) pulls 40 random PYQs, then 1 _complete() call turns them into n_topics strings.
That call itself fails (e.g. the 402 we hit): falls back to zero LLM calls — returns official or [subject_label].
So: 0 or 1 topic-extraction LLM calls per subject, regardless of paper size — this is NOT per-question.

## Case 2 — Topic dedup (_dedupe_topics, fires once per subject after extraction)
Always: 1 embedding call per topic (to check pairwise cosine similarity against already-accepted topics).
Per collision (cosine ≥ 0.78 against an already-picked topic), up to TOPIC_DEDUP_MAX_REFETCH retries:
If unused official-syllabus topics remain: 0 LLM calls — just pop another topic off the list.
If no official topics left (pure PYQ-inferred pool): 1 _complete() call per retry attempt, asking for one replacement topic, plus 1 new embedding call to check the replacement.
Exam mode only: this same function also embeds and compares against every other subject's already-claimed topics in the paper (the Q78/Q83 cross-subject fix) — same call shape, just a bigger comparison pool, no extra call type.

## Case 3 — Per-slot retrieval (fires every question, before drafting)
passage_lookup(): 1 embedding call (_embed), +1 more if RAG_HYDE=1 (the _hyde_expand call turns the topic into a hypothetical-answer sentence before that embedding — so HYDE=1 makes this 2 calls, not 1).
pyq_rag_lookup(): 1 embedding call for the style-example search. No HyDE here — HyDE only applies to book-passage retrieval.
So per slot, first attempt: 2 embedding calls (HyDE off) or 3 (HyDE on, the current server default). No generative LLM call yet — pure retrieval.

## Case 4 — Drafting (fires every question, every attempt)
1 _draft() call per attempt (Sarvam-105b in prod). MAX_SLOT_ATTEMPTS = 3 — so 1 to 3 draft calls per question depending on rejections.

## Case 5 — Mechanical/semantic gates (fire conditionally, after each draft)
validate_question() + guard.check(): pure Python, zero LLM calls.
_ar_explain_check(): only fires when fmt == "assertion" and only after the draft already passed structural validation — 2 embedding calls (A and R statements), no generative call. Not every question hits this — only assertion-format slots.
ground.check(): 1 grounding-judge call (gpt-5.4-nano in prod per the server's .env) — but only reached if validation and the assertion check both passed. A structurally-broken draft never reaches grounding at all.

## Case 6 — Retry branching (determines how many times Cases 3-5 repeat)
Parse/format/validation failure: reason fed back verbatim, same passages reused — next attempt is drafting-only (Case 4 again), no new retrieval calls.
Grounding failure specifically: triggers agentic re-retrieval — a fresh _slot_context() call with wider top_k and the rejected answer's own terms appended to the query. This is a second full Case-3 retrieval (2-3 more embedding calls) before the next draft attempt.
After MAX_SLOT_ATTEMPTS (3) exhausted with no success: slot is dropped, logged in meta, and the top-up loop picks a fresh topic and starts the whole slot over from Case 3 — this is functionally a brand new question's worth of calls, uncapped except by TOPUP_CIRCUIT_BREAKER (sized as "a large multiple of the paper's count," so effectively no ceiling in normal operation).
Putting it together — worked totals
Subject mode, 20 questions, uk-history (no syllabus wiring for this subject — always PYQ-inferred topics), HyDE on, zero retries, zero grounding failures, no assertion-format slots:

1 topic-extraction call
~10 topic-dedup embedding calls (roughly half the topic count typically collides/gets checked — varies)
20 × (2 embed + 1 HyDE) = 60 retrieval-side calls
20 draft calls
20 grounding calls
≈101 embedding/LLM calls total for one clean 20-question run
Exam mode, 100-question vdo-vpdo paper (syllabus-wired), assume ~7 subjects, syllabus fully covers topic needs, HyDE on, a realistic ~15% g