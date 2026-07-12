# -*- coding: utf-8 -*-
"""The two-pass extraction harness — orchestrator.

Ties together the three owned pieces into a workflow that STEERS the model toward
a correct result instead of trusting one big call:

  1. extract_boundaries.find_boundaries  — pass 1, intelligence: where each Q is.
  2. slice_questions.slice_all            — pass 2, dumb code: cut the exact source
                                            lines into {stem, options}. $0, no AI.
  3. validate.validate_question           — mechanical invariant gate: exactly 4
                                            real options, real stem. Pure code.
  4. INFORMED self-correction loop        — any question that fails validation (or
                                            the model marked low-confidence) is
                                            re-read by pass 1 on its LOCAL region,
                                            with the specific failure reason fed
                                            back so the model corrects rather than
                                            re-guesses. Up to _MAX_RETRIES rounds.
  5. Terminal state                       — a question the loop cannot recover
                                            (genuinely unreadable OCR) ships its
                                            BEST-EFFORT slice. The deliverable is
                                            ALWAYS clean (no flags on the paper);
                                            the unrecoverable Q is recorded in the
                                            returned `low_confidence` list so the
                                            DASHBOARD (not the client artifact) can
                                            show it for operator review.

Why this is not the "best-plausible-output fallacy": the old design let the model
guess ONCE, unaware it failed. Here the harness DETECTS the failure mechanically
and FEEDS IT BACK; the model only lands on best-effort after the loop is
exhausted — i.e. genuinely the best it can do, not a lazy first guess.

Contract: `extract_two_pass(text) -> {"questions":[{n,stem,options}], "low_confidence":[{n,reason}]}`.
Same `questions` shape the rest of the pipeline consumes; `low_confidence` is new
metadata for the worker to thread into the job meta.
"""
from __future__ import annotations

import sys

import extract_boundaries as eb
import slice_questions as sq
import validate as vd


# How many informed re-reads a single failing question gets before it ships
# best-effort. Small — each retry is a cheap boundary-only call, but a genuinely
# unreadable question won't improve past 2-3 tries.
_MAX_RETRIES = 3
# Context lines to include above/below a failing question's range when re-reading,
# so the model can see an option that spilled onto an adjacent line.
_RETRY_CONTEXT = 4


def _region_text(raw_lines: list[str], start: int, end: int) -> tuple[str, int]:
    """Line-numbered text of a question's local region (± context), and the
    absolute line number the region starts at (to map local→absolute back)."""
    lo = max(1, start - _RETRY_CONTEXT)
    hi = min(len(raw_lines), end + _RETRY_CONTEXT)
    numbered = "\n".join(f"[{i}] {raw_lines[i - 1]}" for i in range(lo, hi + 1))
    return numbered, lo


def _retry_question(raw_lines: list[str], b: dict, reason: str) -> dict | None:
    """One informed re-read of a single failing question. Handles BOTH failure
    classes:
      1. BOUNDARY error — pass 1 cut the question wrong. Re-ask pass 1; if it
         returns a DIFFERENT range, re-slice it (deterministic markers may now
         parse cleanly).
      2. MARKER-PARSE error — the boundary is right but the slicer can't read a
         garbled option marker (Sarvam ";ंद्ध" for "(a)"). Re-asking the boundary
         is useless (same range, same garble). Detect this (range unchanged +
         still short) and escalate to a narrow content-read of ONLY this
         question's options, verbatim.
    Returns a freshly built question dict, or None if nothing usable came back."""
    region, _ = _region_text(raw_lines, b["start_line"], b["end_line"])
    old_start, old_end = b["start_line"], b["end_line"]

    fixed = eb.refind_one(region, b.get("n"), reason)
    if fixed:
        b["start_line"], b["end_line"] = fixed["start_line"], fixed["end_line"]
        q = sq.slice_question(raw_lines, fixed["start_line"], fixed["end_line"],
                              n=b.get("n"))
        q["_confidence"] = fixed.get("confidence", "high")
        # If the boundary actually MOVED, a re-slice may have fixed it — return it.
        if (fixed["start_line"], fixed["end_line"]) != (old_start, old_end):
            return q
        # Boundary unchanged AND still short -> this is a marker-parse failure.
        if len(q.get("options", [])) != vd.EXPECTED_OPTIONS:
            region2, _ = _region_text(raw_lines, b["start_line"], b["end_line"])
            opts = eb.reread_options(region2, b.get("n"))
            if opts and len(opts) == vd.EXPECTED_OPTIONS:
                q["options"] = opts
                q["_confidence"] = "high"
            return q
        return q

    # pass 1 returned nothing -> try the content-read directly on the current range
    opts = eb.reread_options(region, b.get("n"))
    if opts:
        q = sq.slice_question(raw_lines, b["start_line"], b["end_line"], n=b.get("n"))
        if len(opts) == vd.EXPECTED_OPTIONS:
            q["options"] = opts
            q["_confidence"] = "high"
        return q
    return None


def extract_two_pass(text: str) -> dict:
    """Run the full two-pass harness. See module docstring for the contract."""
    if not text or not text.strip():
        raise ValueError("two_pass: empty text")

    raw_lines, _ = eb.number_lines(text)
    boundaries, estimated = eb.find_boundaries(text)
    if not boundaries:
        raise ValueError("two_pass: pass 1 returned no boundaries")

    # Cross-check count against the deterministic estimate; a big shortfall means
    # pass 1 missed whole questions — log it (the loop can't recover a question
    # that was never bounded, but the operator should see the discrepancy).
    count_note = None
    if estimated >= 10 and len(boundaries) < estimated - max(2, round(estimated * 0.05)):
        count_note = (f"pass 1 found {len(boundaries)} questions but the paper "
                      f"numbers ~{estimated}")
        print(f"  [two_pass] WARNING: {count_note}", file=sys.stderr)

    questions = sq.slice_all(raw_lines, boundaries)

    low_confidence: list[dict] = []
    for idx, q in enumerate(questions):
        b = boundaries[idx]
        reason = vd.validate_question(q)
        low_conf = q.get("_confidence") == "low"
        if reason is None and not low_conf:
            continue

        # INFORMED self-correction loop for this one question.
        attempts = 0
        while attempts < _MAX_RETRIES and (reason is not None or low_conf):
            attempts += 1
            fed_back = reason or "the extraction was marked low-confidence; re-read carefully"
            retried = _retry_question(raw_lines, b, fed_back)
            if retried is not None:
                # keep the better result (more options / not-low-confidence)
                retried_reason = vd.validate_question(retried)
                if retried_reason is None:
                    questions[idx] = retried
                    reason, low_conf = None, retried["_confidence"] == "low"
                    break
                # partial improvement (e.g. 3->4 opts still short): adopt if it has
                # more options than what we had, keep looping with the new reason
                if len(retried.get("options", [])) > len(q.get("options", [])):
                    questions[idx] = q = retried
                reason = retried_reason
                low_conf = retried.get("_confidence") == "low"
            # if retry returned nothing, loop again (bounded) with same feedback

        # Terminal: still not clean after the loop -> ship best-effort, record it
        # for the dashboard. The question STAYS in `questions` (clean deliverable,
        # no flag on the paper); only the side-channel notes it.
        final = questions[idx]
        final_reason = vd.validate_question(final)
        if final_reason is not None or final.get("_confidence") == "low":
            low_confidence.append({
                "n": final.get("n"),
                "reason": final_reason or "model low-confidence after informed retries",
            })

    # strip the internal _confidence marker before returning
    for q in questions:
        q.pop("_confidence", None)

    out = {"questions": questions, "low_confidence": low_confidence}
    if count_note:
        out["count_note"] = count_note
    return out
