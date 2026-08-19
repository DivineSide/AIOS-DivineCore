# -*- coding: utf-8 -*-
"""
latency_test_server.py — run ON the Hetzner server: fair repeated-trial
latency comparison of e5-base (self-hosted, warm) vs OpenAI text-embedding-3-small
(API), for single LIVE QUERY embeds (not bulk passage encoding — that's a
separate, already-measured one-time cost). This is the number that actually
matters for "does switching slow down live paper generation."
"""
import os
import statistics
import time

from dotenv import load_dotenv

load_dotenv("/root/.env")

QUERIES = [
    "उत्तराखंड का प्रथम राज्यपाल कौन था?",
    "चंद्रमा का पर्यायवाची शब्द नहीं है",
    "भारत में हरित क्रांति के जनक कौन थे?",
    "उत्तराखंड में पंचायती राज व्यवस्था कब लागू हुई?",
    "हिंदी व्याकरण में कारक के कितने भेद होते हैं?",
    "भारतीय संविधान का कौन सा अनुच्छेद मौलिक अधिकारों से संबंधित है?",
    "गढ़वाल और कुमाऊं के बीच मुख्य अंतर क्या है?",
    "कंप्यूटर की प्राथमिक मेमोरी किसे कहते हैं?",
    "उत्तराखंड राज्य का गठन किस वर्ष हुआ था?",
    "भारत में प्रथम पंचवर्षीय योजना कब शुरू हुई?",
]

N_TRIALS = 10


def test_e5():
    print("\n=== e5-base (self-hosted, warm) ===", flush=True)
    t0 = time.time()
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("intfloat/multilingual-e5-base")
    print(f"cold model load: {time.time()-t0:.2f}s", flush=True)

    # warm-up call (first real call always pays extra kernel-init cost)
    m.encode("query: warmup", normalize_embeddings=True, show_progress_bar=False)

    times = []
    for i in range(N_TRIALS):
        q = QUERIES[i % len(QUERIES)]
        t0 = time.time()
        m.encode("query: " + q, normalize_embeddings=True, show_progress_bar=False)
        dt = time.time() - t0
        times.append(dt)
        print(f"  trial {i+1}: {dt:.3f}s", flush=True)

    print(f"e5-base warm — mean: {statistics.mean(times):.3f}s  "
          f"median: {statistics.median(times):.3f}s  "
          f"stdev: {statistics.stdev(times):.3f}s  "
          f"min: {min(times):.3f}s  max: {max(times):.3f}s", flush=True)
    return times


def test_openai():
    print("\n=== OpenAI text-embedding-3-small (API) ===", flush=True)
    from openai import OpenAI
    client = OpenAI()

    times = []
    for i in range(N_TRIALS):
        q = QUERIES[i % len(QUERIES)]
        t0 = time.time()
        try:
            client.embeddings.create(model="text-embedding-3-small", input=q)
            dt = time.time() - t0
            times.append(dt)
            print(f"  trial {i+1}: {dt:.3f}s", flush=True)
        except Exception as e:
            print(f"  trial {i+1}: FAILED ({str(e)[:80]})", flush=True)

    if times:
        print(f"OpenAI — mean: {statistics.mean(times):.3f}s  "
              f"median: {statistics.median(times):.3f}s  "
              f"stdev: {statistics.stdev(times) if len(times) > 1 else 0:.3f}s  "
              f"min: {min(times):.3f}s  max: {max(times):.3f}s", flush=True)
    else:
        print("OpenAI — all trials failed", flush=True)
    return times


if __name__ == "__main__":
    e5_times = test_e5()
    oai_times = test_openai()

    print("\n=== SUMMARY ===", flush=True)
    if e5_times:
        print(f"e5-base   mean: {statistics.mean(e5_times):.3f}s", flush=True)
    if oai_times:
        print(f"OpenAI    mean: {statistics.mean(oai_times):.3f}s", flush=True)
