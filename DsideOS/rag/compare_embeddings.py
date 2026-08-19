# -*- coding: utf-8 -*-
"""
compare_embeddings.py — one-time LOCAL script: side-by-side retrieval-quality
comparison of OpenAI text-embedding-3-small vs. BAAI/bge-m3 vs.
intfloat/multilingual-e5-base, on THIS corpus (not a generic benchmark).

Ground truth: real pyq_chunks rows (actual historical exam questions) are used
as queries. For each PYQ, we don't have a labeled "correct passage" — instead
we use a self-retrieval proxy: embed the PYQ's own chunk_text as the query,
search book_passages, and score how well each model surfaces passages from
the SAME subject with high similarity. This isn't perfect ground truth, but
it's a real, non-fabricated relative signal: a good embedding model should
reliably pull same-subject passages to the top and separate them from
other-subject noise. We report:
  - subject-match rate @ top-5 (does the correct subject dominate top results?)
  - mean top-1 similarity score
  - qualitative dump of top-3 hits per query for manual eyeballing

Does NOT write to Supabase. Does NOT touch book_passages/pyq_chunks. Pulls a
sample into memory, embeds locally with each candidate model + OpenAI's API,
and compares. Meant to be read by a human before committing to a bulk re-embed.

Usage:
    python compare_embeddings.py --subject hindi --n 15
    python compare_embeddings.py --all-subjects --n 8
"""

import argparse
import io
import os
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)

import psycopg2
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
SUBJECTS = ["hindi", "computer", "uk-history", "uk-culture",
            "uk-geography", "uk-general-studies", "general-gk"]


def _load_env():
    for candidate in [BASE.parent.parent / ".env", BASE.parent / ".env", BASE / ".env"]:
        if candidate.exists():
            load_dotenv(candidate)
            return
    raise RuntimeError("no .env found")


def _db():
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=15)


def sample_queries(conn, subject: str, n: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, chunk_text FROM pyq_chunks WHERE subject = %s ORDER BY random() LIMIT %s",
            (subject, n),
        )
        return [{"id": r[0], "text": r[1], "subject": subject} for r in cur.fetchall()]


def sample_corpus(conn, subjects: list[str], per_subject: int) -> list[dict]:
    """Pull a fixed passage pool (same pool used for every model, so the
    comparison is apples-to-apples) — not the full 19k corpus, that's
    unnecessary for a quality signal and slow to embed 3x on CPU."""
    passages = []
    with conn.cursor() as cur:
        for subj in subjects:
            cur.execute(
                "SELECT id, subject, passage_text FROM book_passages "
                "WHERE subject = %s ORDER BY random() LIMIT %s",
                (subj, per_subject),
            )
            for r in cur.fetchall():
                passages.append({"id": r[0], "subject": r[1], "text": r[2]})
    return passages


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def embed_openai(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI()
    out = []
    # batch in chunks of 100 to stay well under request size limits
    for i in range(0, len(texts), 100):
        resp = client.embeddings.create(model="text-embedding-3-small", input=texts[i:i + 100])
        out.extend([d.embedding for d in resp.data])
    return out


def embed_st(model, texts: list[str], query_prefix: str = "", passage_prefix: str = "",
             is_query: bool = False) -> list[list[float]]:
    prefix = query_prefix if is_query else passage_prefix
    prefixed = [prefix + t for t in texts] if prefix else texts
    embs = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False, batch_size=16)
    return [e.tolist() for e in embs]


def evaluate(name: str, query_embs: dict, corpus_embs: list[dict], queries: list[dict], top_k: int = 5):
    """query_embs: {query_id: embedding}; corpus_embs: [{"id","subject","embedding"}]"""
    subject_match_at_5 = 0
    top1_sims = []
    dumps = []
    for q in queries:
        qemb = query_embs[q["id"]]
        scored = sorted(
            corpus_embs,
            key=lambda c: _cosine(qemb, c["embedding"]),
            reverse=True,
        )
        top5 = scored[:top_k]
        same_subj = sum(1 for c in top5 if c["subject"] == q["subject"])
        if same_subj >= 3:  # majority of top-5 from correct subject
            subject_match_at_5 += 1
        top1_sims.append(_cosine(qemb, scored[0]["embedding"]))
        dumps.append({
            "query": q["text"][:120],
            "subject": q["subject"],
            "top3": [(c["subject"], c["text"][:90], round(_cosine(qemb, c["embedding"]), 3)) for c in scored[:3]],
        })

    n = len(queries)
    print(f"\n=== {name} ===")
    print(f"  subject-match@5 (>=3/5 correct subject): {subject_match_at_5}/{n} ({100*subject_match_at_5/n:.0f}%)")
    print(f"  mean top-1 similarity: {sum(top1_sims)/n:.4f}")
    return dumps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", choices=SUBJECTS)
    ap.add_argument("--all-subjects", action="store_true")
    ap.add_argument("--n", type=int, default=10, help="queries per subject")
    ap.add_argument("--corpus-per-subject", type=int, default=40)
    ap.add_argument("--dump", action="store_true", help="print top-3 hits per query")
    ap.add_argument("--models", default="openai,bge,e5",
                     help="comma list from {openai,bge,e5} — skip models you can't/don't want to run "
                          "(e.g. --models e5 when OpenAI credits are exhausted)")
    args = ap.parse_args()
    wanted = set(args.models.split(","))

    _load_env()
    conn = _db()

    subjects = SUBJECTS if args.all_subjects else [args.subject or "hindi"]

    queries = []
    for s in subjects:
        queries.extend(sample_queries(conn, s, args.n))
    corpus = sample_corpus(conn, subjects, args.corpus_per_subject)
    print(f"Loaded {len(queries)} queries, {len(corpus)} corpus passages across {subjects}")

    query_texts = [q["text"] for q in queries]
    corpus_texts = [c["text"] for c in corpus]

    print("\nLoading models...")
    from sentence_transformers import SentenceTransformer

    candidates = []

    if "openai" in wanted:
        print("Embedding with OpenAI text-embedding-3-small...")
        oai_q = embed_openai(query_texts)
        oai_c = embed_openai(corpus_texts)
        candidates.append(("OpenAI text-embedding-3-small", oai_q, oai_c))

    if "bge" in wanted:
        bge = SentenceTransformer("BAAI/bge-m3")
        print("Embedding with BGE-M3...")
        bge_q = embed_st(bge, query_texts)
        bge_c = embed_st(bge, corpus_texts)
        candidates.append(("BAAI/bge-m3", bge_q, bge_c))

    if "e5" in wanted:
        e5 = SentenceTransformer("intfloat/multilingual-e5-base")
        print("Embedding with multilingual-e5-base (query/passage prefixes per model card)...")
        e5_q = embed_st(e5, query_texts, query_prefix="query: ", is_query=True)
        e5_c = embed_st(e5, corpus_texts, passage_prefix="passage: ", is_query=False)
        candidates.append(("intfloat/multilingual-e5-base", e5_q, e5_c))

    results = {}
    for name, qembs, cembs in candidates:
        query_emb_map = {q["id"]: e for q, e in zip(queries, qembs)}
        corpus_emb_list = [{"id": c["id"], "subject": c["subject"], "text": c["text"], "embedding": e}
                            for c, e in zip(corpus, cembs)]
        dumps = evaluate(name, query_emb_map, corpus_emb_list, queries)
        results[name] = dumps

    if args.dump:
        print("\n\n=== SAMPLE QUALITATIVE DUMPS (first 5 queries) ===")
        for i in range(min(5, len(queries))):
            print(f"\nQuery [{queries[i]['subject']}]: {queries[i]['text'][:150]}")
            for name in results:
                print(f"  -- {name} --")
                for subj, txt, sim in results[name][i]["top3"]:
                    print(f"     ({sim}) [{subj}] {txt}")


if __name__ == "__main__":
    main()
