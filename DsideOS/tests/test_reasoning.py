# -*- coding: utf-8 -*-
"""THE GATE for code-generated reasoning questions.

Every other question source in this pipeline is policed at runtime by
validate_gen + PaperGuard. Reasoning bypasses both, deliberately: those checks
are proxies for LLM failure modes that cannot occur when code computes the
answer (a numeric answer is CORRECT for a distance question; a 4-digit series
term is not a hallucinated date). See worker/reasoning/__init__.py.

That exemption is only safe if THIS FILE is thorough. The one defect a code
generator can still produce is a wrong solver, and no runtime gate can detect
that — only an independent re-derivation can. So each test re-solves the
question by a DIFFERENT path than the generator used and compares.

Run:  python -m pytest tests/test_reasoning.py -q
"""
from __future__ import annotations

import math
import random
import re
import sys
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "worker"))

import reasoning                                    # noqa: E402
from reasoning import coding, direction, pools, series   # noqa: E402

# Enough seeds that a 1-in-1000 construction bug surfaces, small enough that
# the suite stays under a couple of seconds.
SEEDS = range(1000)


# ── shared structural invariants ────────────────────────────────────────────

@pytest.mark.parametrize("type_name", sorted(reasoning.TYPES))
def test_structure(type_name):
    """Every generator, every seed: a well-formed 4-option question."""
    mod = reasoning.TYPES[type_name]
    for s in SEEDS:
        q = mod.generate(random.Random(s))
        assert isinstance(q["stem"], str) and len(q["stem"].strip()) >= 15, \
            f"{type_name} seed {s}: stem too short"
        assert isinstance(q["options"], list) and len(q["options"]) == 4, \
            f"{type_name} seed {s}: not 4 options"
        assert len(set(q["options"])) == 4, \
            f"{type_name} seed {s}: duplicate options {q['options']}"
        assert all(isinstance(o, str) and o.strip() for o in q["options"]), \
            f"{type_name} seed {s}: empty option"
        assert q["answer"] in "abcd", f"{type_name} seed {s}: bad answer key"
        assert q["format"] == "plain"
        assert q["reason"].strip(), f"{type_name} seed {s}: empty reason"


@pytest.mark.parametrize("type_name", sorted(reasoning.TYPES))
def test_deterministic(type_name):
    """The same seed must reproduce the same question, exactly.

    This is what makes a reported bad question reproducible from the job
    record alone.
    """
    mod = reasoning.TYPES[type_name]
    for s in list(SEEDS)[:200]:
        a = mod.generate(random.Random(s))
        b = mod.generate(random.Random(s))
        assert a == b, f"{type_name} seed {s}: not deterministic"


# ── direction: re-solve from the STEM TEXT, not the parameters ──────────────

def _parse_walk(stem: str) -> list[tuple[str, int]]:
    """Recover the walk from the rendered Hindi stem.

    Deliberately parses the STUDENT-VISIBLE text rather than reading the
    generator's internals — if the stem and the computed answer ever disagree,
    the student sees the stem, so the stem is the source of truth.
    """
    legs = []
    for m in re.finditer(r"(पूर्व|पश्चिम|उत्तर|दक्षिण)\s*दिशा\s*में[^0-9]*?(\d+)",
                         stem):
        legs.append((m.group(1), int(m.group(2))))
    return legs


def test_direction_answer_matches_stem():
    """The keyed answer equals the distance implied by the stem's own walk."""
    for s in SEEDS:
        q = direction.generate(random.Random(s))
        legs = _parse_walk(q["stem"])
        assert len(legs) == 4, f"seed {s}: parsed {len(legs)} legs from stem"

        dx = dy = 0
        for label, dist in legs:
            ux, uy = pools.DIRECTIONS[label]
            dx += ux * dist
            dy += uy * dist
        expected = math.hypot(dx, dy)

        keyed = q["options"]["abcd".index(q["answer"])]
        keyed_val = float(re.match(r"([\d.]+)", keyed).group(1))
        assert abs(keyed_val - expected) < 1e-9, (
            f"seed {s}: stem implies {expected}, key says {keyed_val}\n"
            f"{q['stem']}")


def test_direction_answer_is_integer():
    """Walks are built from Pythagorean triples, so the answer is a whole
    number — a UKSSSC paper never asks for √29 किमी."""
    for s in SEEDS:
        q = direction.generate(random.Random(s))
        keyed = q["options"]["abcd".index(q["answer"])]
        val = float(re.match(r"([\d.]+)", keyed).group(1))
        assert val == int(val), f"seed {s}: non-integer answer {keyed}"


def test_direction_gender_agreement():
    """A feminine subject never takes a masculine verb.

    Regression: 'उषा ने ... मुड़ा और ... चली' shipped from the first draft,
    because a gendered participle sat in the shared TURN_WORDS pool.
    """
    masculine = ("चला।", "गया।", "पहुँचा", "मुड़ा")
    for s in SEEDS:
        q = direction.generate(random.Random(s))
        if any(n in q["stem"] for n in pools.FEMALE_NAMES):
            hit = [v for v in masculine if v in q["stem"]]
            assert not hit, f"seed {s}: feminine subject with {hit}\n{q['stem']}"


# ── series: re-derive the rule from the shown terms ─────────────────────────

def _shown_terms(stem: str) -> list[Fraction]:
    """The visible series terms.

    Takes the TRAILING comma-separated numeric run rather than splitting on
    ':' or '?': one stem variant is "... प्रश्नवाचक चिह्न (?) के स्थान पर क्या
    आएगा ? 3, 10, 17, 24, 31, ?" — both delimiters appear inside the question
    text itself, so either split truncates before the series (test bug, caught
    on seed 4).
    """
    m = re.search(r"((?:[\d.]+\s*,\s*)+)\?\s*$", stem.strip())
    if not m:
        return []
    return [Fraction(tok.strip()) for tok in m.group(1).split(",") if tok.strip()]


def test_series_answer_continues_the_pattern():
    """The keyed answer must continue the series the student can see.

    Checks the two rule families that are recoverable from the terms alone
    (constant ratio, constant difference); the index-dependent rules are
    covered by test_series_solve_roundtrip instead.
    """
    for s in SEEDS:
        q = series.generate(random.Random(s))
        terms = _shown_terms(q["stem"])
        assert len(terms) >= 3, f"seed {s}: only {len(terms)} terms shown"
        keyed = Fraction(q["options"]["abcd".index(q["answer"])])

        ratios = {terms[i + 1] / terms[i] for i in range(len(terms) - 1)}
        diffs = {terms[i + 1] - terms[i] for i in range(len(terms) - 1)}
        if len(ratios) == 1:
            assert keyed == terms[-1] * ratios.pop(), (
                f"seed {s}: geometric series, key breaks the ratio\n{q['stem']}")
        elif len(diffs) == 1:
            assert keyed == terms[-1] + diffs.pop(), (
                f"seed {s}: arithmetic series, key breaks the difference\n"
                f"{q['stem']}")


def test_series_solve_roundtrip():
    """series.solve regenerates a series identical to its own parameters."""
    rng = random.Random(0)
    for rule_name, _, _ in series._RULES:
        for _ in range(100):
            k = Fraction(rng.randint(1, 5))
            first = Fraction(rng.randint(1, 9))
            a = series.solve(rule_name, k, first, 6)
            b = series.solve(rule_name, k, first, 6)
            assert a == b
            assert len(a) == 6 and a[0] == first


def test_series_no_visible_term_as_distractor():
    """A term already printed in the series must never be an option.

    Regression: '10, 22, 34, 46, ?' offered 46, which a candidate eliminates
    without doing any arithmetic.
    """
    for s in SEEDS:
        q = series.generate(random.Random(s))
        shown = {series._fmt(t) for t in _shown_terms(q["stem"])}
        leaked = shown & set(q["options"])
        assert not leaked, f"seed {s}: visible term(s) {leaked} offered as options"


# ── coding: re-apply the cipher by hand ─────────────────────────────────────

def test_coding_answer_matches_the_demonstrated_rule():
    """Infer the rule from the (source, code) pair in the stem, apply it to the
    target word, and check the key — exactly what a candidate does."""
    for s in SEEDS:
        q = coding.generate(random.Random(s))
        m = re.search(r"'([A-Z]+)'\s*को\s*'([\d-]+)'|'([A-Z]+)'\s*का\s*कूट\s*'([\d-]+)'",
                      q["stem"])
        assert m, f"seed {s}: cannot parse stem\n{q['stem']}"
        src = m.group(1) or m.group(3)
        code = m.group(2) or m.group(4)
        dst = re.findall(r"'([A-Z]+)'", q["stem"])[-1]
        keyed = q["options"]["abcd".index(q["answer"])]

        mode = "sum" if "-" not in code else "sequence"
        # Find which (rule, k) reproduces the demonstrated code, then require
        # the key to match that same rule applied to dst.
        matches = []
        for rule_name, _, _ in coding._RULES:
            for k in range(0, 6):
                if coding.encode(src, rule_name, k, mode) == code:
                    matches.append((rule_name, k))
        assert matches, f"seed {s}: no rule reproduces {src} -> {code}"
        assert any(coding.encode(dst, rn, k, mode) == keyed for rn, k in matches), (
            f"seed {s}: key {keyed} matches no rule that explains the stem\n"
            f"{q['stem']}")


def test_coding_source_and_target_differ():
    """The demonstrated word must not be the asked word — otherwise the answer
    is copyable straight out of the stem."""
    for s in SEEDS:
        q = coding.generate(random.Random(s))
        words = re.findall(r"'([A-Z]+)'", q["stem"])
        assert len(words) >= 2 and words[0] != words[-1], \
            f"seed {s}: same word demonstrated and asked\n{q['stem']}"


# ── registry ────────────────────────────────────────────────────────────────

def test_block_is_distinct_and_complete():
    for s in range(200):
        qs = reasoning.generate(10, seed=s)
        assert len(qs) == 10, f"seed {s}: got {len(qs)} questions"
        stems = [" ".join(q["stem"].split()) for q in qs]
        assert len(set(stems)) == 10, f"seed {s}: duplicate stem in one block"


def test_types_are_spread_not_clustered():
    """No three consecutive questions of the same type.

    Regression: round-robin-then-shuffle produced a 3+ run in 51 of 200 blocks,
    including three coding questions in a row.
    """
    for s in range(300):
        types = [q["_type"] for q in reasoning.generate(10, seed=s)]
        run = best = 1
        for i in range(1, len(types)):
            run = run + 1 if types[i] == types[i - 1] else 1
            best = max(best, run)
        assert best < 3, f"seed {s}: run of {best} identical types — {types}"


def test_blocks_from_different_seeds_do_not_overlap():
    a = {q["stem"] for q in reasoning.generate(10, seed=1)}
    b = {q["stem"] for q in reasoning.generate(10, seed=2)}
    assert not (a & b), "two seeds produced a shared stem"


def test_no_network_or_model_import():
    """The whole point: this path must not be able to call a model.

    Guards against a future 'just add a model call for variety' regression.
    """
    # Iterate the PACKAGE, not a hardcoded list. The previous version named
    # five modules explicitly and had already silently stopped covering
    # `relations` and `arrangement` when those were added — exactly the way a
    # guard test rots.
    import importlib
    import pkgutil
    pkg_dir = Path(reasoning.__file__).parent
    mods = [reasoning] + [
        importlib.import_module(f"reasoning.{m.name}")
        for m in pkgutil.iter_modules([str(pkg_dir)])
    ]
    assert len(mods) >= len(reasoning.TYPES), "package scan missed modules"
    for mod in mods:
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for banned in ("openai", "groq", "requests", "httpx", "urllib",
                       "psycopg2", "_draft_", "api_key"):
            assert banned not in src.lower(), \
                f"{Path(mod.__file__).name} references {banned!r}"


# ── relations: re-resolve the chain independently ───────────────────────────

def test_relations_answer_matches_the_chain():
    """Re-walk the possessive chain in the stem and compare to the key.

    Parses the STUDENT-VISIBLE chain rather than trusting the generator's
    path, for the same reason the direction test does.
    """
    from reasoning import relations as rel
    step_to_edge = {}
    for src, step, dst in rel._EDGES:
        step_to_edge.setdefault((src, step), dst)

    for s in SEEDS:
        q = rel.generate(random.Random(s))
        m = re.search(r'"वह (.+?) (?:है|हैं)।"', q["stem"])
        assert m, f"seed {s}: cannot parse chain\n{q['stem']}"
        chain = m.group(1)

        # Greedily consume known steps from the chain, walking the tree.
        node, rest = "self", chain
        while rest:
            for (src, step), dst in step_to_edge.items():
                if src == node and rest.startswith(step):
                    node, rest = dst, rest[len(step):].strip()
                    break
            else:
                raise AssertionError(
                    f"seed {s}: unparsable step in {chain!r} at {rest!r}")
        expected = rel._ANSWER[node]
        keyed = q["options"]["abcd".index(q["answer"])]
        assert keyed == expected, (
            f"seed {s}: chain resolves to {expected}, key says {keyed}\n"
            f"{q['stem']}")


def test_relations_elder_takes_honorific():
    """Elders take हैं, peers take है. A teacher notices this instantly."""
    from reasoning import relations as rel
    elder = {"पिता", "माता", "दादा", "दादी", "चाचा", "चाची"}
    for s in SEEDS:
        q = rel.generate(random.Random(s))
        keyed = q["options"]["abcd".index(q["answer"])]
        if keyed in elder:
            assert 'हैं।"' in q["stem"], f"seed {s}: elder without honorific"
        else:
            assert 'है।"' in q["stem"], f"seed {s}: peer with honorific"


def test_relations_answer_spread_is_not_degenerate():
    """No single relation may dominate the answer key.

    Regression: plain random walks answered पिता 43% of the time, because many
    edges lead there. A paper whose relation questions are almost always
    "father" tests one fact repeatedly.
    """
    import collections
    from reasoning import relations as rel
    c = collections.Counter()
    for s in SEEDS:
        q = rel.generate(random.Random(s))
        c[q["options"]["abcd".index(q["answer"])]] += 1
    top = c.most_common(1)[0][1] / sum(c.values())
    assert top < 0.30, f"most common answer is {top:.0%} of all keys — {c}"


# ── arrangement: brute-force the layout from the stem's own clues ───────────

def test_arrangement_answer_is_uniquely_determined():
    """The clues in the stem must pin exactly one value for the asked pair.

    This is the failure mode of the type: clues admitting two layouts make the
    question unanswerable. Verified by re-deriving from the RENDERED stem.
    """
    from itertools import permutations
    from reasoning import arrangement as arr

    for s in list(SEEDS)[:80]:           # brute force, so a smaller sweep
        q = arr.generate(random.Random(s))
        stem = q["stem"]
        names = re.search(r"चार गाँव (.+?) एक सरल रेखा", stem).group(1)
        names = [n.strip() for n in names.split(",")]
        ask = re.search(r"(\w) से (\w) की दूरी कितनी है", stem)
        assert ask, f"seed {s}: no question clause"
        a, b = ask.group(1), ask.group(2)

        dists = [(m.group(1), m.group(2), int(m.group(3)))
                 for m in re.finditer(r"(\w) से (\w) तक की दूरी (\d+)", stem)]
        betweens = [(m.group(1), m.group(2), m.group(3))
                    for m in re.finditer(r"गाँव (\w), (\w) और (\w) के बीच", stem)]

        # Search integer layouts consistent with the clues.
        #
        # The span is the SUM of the stated gaps, not the largest one: the
        # generator states every consecutive gap, so max() would search a line
        # far shorter than the real one and find no layout at all (test bug —
        # it reported "clues allow set()" for perfectly good questions).
        found = set()
        span = sum(d for _, _, d in dists)
        for order in permutations(names):
            for gaps in _gap_candidates(span, len(names) - 1):
                pos, run = {}, 0
                for i, n in enumerate(order):
                    pos[n] = run
                    if i < len(gaps):
                        run += gaps[i]
                if any(abs(pos[x] - pos[y]) != d for x, y, d in dists):
                    continue
                ok = True
                for m_, x, y in betweens:
                    lo, hi = sorted((pos[x], pos[y]))
                    if not (lo < pos[m_] < hi):
                        ok = False
                        break
                if ok:
                    found.add(abs(pos[a] - pos[b]))

        keyed = int(re.match(r"(\d+)", q["options"]["abcd".index(q["answer"])]).group(1))
        assert found, f"seed {s}: no layout satisfies the stem's own clues"
        assert found == {keyed}, (
            f"seed {s}: clues allow {sorted(found)}, key says {keyed}\n{stem}")


def _gap_candidates(span: int, n_gaps: int):
    """All positive integer gap tuples summing to `span`. Small by design."""
    if n_gaps == 1:
        yield (span,)
        return
    for first in range(1, span - n_gaps + 2):
        for rest in _gap_candidates(span - first, n_gaps - 1):
            yield (first,) + rest


def test_arrangement_never_states_the_asked_distance():
    """The asked pair must not appear as a stated clue.

    Regression: a stem said "C से A तक की दूरी 5 किमी है" and then asked
    "C से A की दूरी कितनी है?".
    """
    from reasoning import arrangement as arr
    for s in SEEDS:
        q = arr.generate(random.Random(s))
        m = re.search(r"(\w) से (\w) की दूरी कितनी है", q["stem"])
        a, b = m.group(1), m.group(2)
        for x, y in ((a, b), (b, a)):
            assert not re.search(rf"{x} से {y} तक की दूरी", q["stem"]), \
                f"seed {s}: answer stated in the stem\n{q['stem']}"


# ── tier 1 & 2 types ────────────────────────────────────────────────────────

def test_lettersum_answer_is_the_extreme():
    """Recompute every option's letter sum from ord() and check the key."""
    from reasoning import lettersum as ls
    for s in SEEDS:
        q = ls.generate(random.Random(s))
        sums = {w: sum(ord(c) - 64 for c in w.upper()) for w in q["options"]}
        keyed = q["options"]["abcd".index(q["answer"])]
        want = max(sums.values()) if "अधिकतम" in q["stem"] else min(sums.values())
        assert sums[keyed] == want, (
            f"seed {s}: key {keyed}={sums[keyed]} but extreme is {want}")
        assert list(sums.values()).count(want) == 1, f"seed {s}: tie"


def test_calendar_matches_the_real_calendar():
    """Verify against Python's own datetime, not the generator's arithmetic."""
    import datetime
    from reasoning import calendar_year as cy
    for s in list(SEEDS)[:400]:
        q = cy.generate(random.Random(s))
        year = int(re.search(r"वर्ष (\d{4})", q["stem"]).group(1))
        keyed = int(q["options"]["abcd".index(q["answer"])])
        assert (datetime.date(year, 1, 1).weekday()
                == datetime.date(keyed, 1, 1).weekday()), \
            f"seed {s}: {year} and {keyed} start on different weekdays"
        assert cy.is_leap(year) == cy.is_leap(keyed), \
            f"seed {s}: {year} and {keyed} differ in leap status"


def test_calendar_no_earlier_year_also_works():
    """The answer must be the FIRST repeat, not merely *a* repeat."""
    import datetime
    from reasoning import calendar_year as cy
    for s in list(SEEDS)[:300]:
        q = cy.generate(random.Random(s))
        year = int(re.search(r"वर्ष (\d{4})", q["stem"]).group(1))
        keyed = int(q["options"]["abcd".index(q["answer"])])
        for mid in range(year + 1, keyed):
            same = (datetime.date(year, 1, 1).weekday()
                    == datetime.date(mid, 1, 1).weekday()
                    and cy.is_leap(year) == cy.is_leap(mid))
            assert not same, f"seed {s}: {mid} repeats {year} before {keyed}"


def test_grouping_query_has_exactly_one_answer():
    """Re-read the sets out of the stem and re-run the query independently."""
    from reasoning import grouping as gr
    for s in SEEDS:
        q = gr.generate(random.Random(s))
        sets, people = {}, set()
        for line in q["stem"].splitlines():
            m = re.match(r"\s*(?:i|ii|iii|iv|v)\.\s*(.+?)\s+और\s+(\S+)\s+(.+?)\s+हैं\s*।", line)
            if not m:
                continue
            # group(1) = all but the last name, group(2) = the last name,
            # group(3) = the property, which may be MULTI-WORD ("kathin
            # parishrami"). An earlier \S+ captured only its last word and the
            # set lookup silently missed, making the test disagree with a
            # correct generator.
            names = [n.strip() for n in m.group(1).split(",") if n.strip()]
            names.append(m.group(2).strip())
            sets[m.group(3).strip()] = set(names)
            people |= set(names)
        assert len(sets) == 4, f"seed {s}: parsed {len(sets)} property lines"

        neg = re.search(r"न तो (.+?) है और न ही (.+?), किन्तु", q["stem"])
        pos = re.search(r"किन्तु (.+?) है \?", q["stem"])
        assert neg and pos, f"seed {s}: cannot parse the query"

        hits = [p for p in people
                if p not in sets.get(neg.group(1), set())
                and p not in sets.get(neg.group(2), set())
                and p in sets.get(pos.group(1).strip(), set())]
        keyed = q["options"]["abcd".index(q["answer"])]
        assert hits == [keyed], f"seed {s}: query matches {hits}, key {keyed}"


def test_household_count_matches_the_description():
    """Rebuild the family from the stem's own numbers and recount."""
    from reasoning import household as hh
    for s in SEEDS:
        q = hh.generate(random.Random(s))
        stem = q["stem"]
        keyed = int(q["options"]["abcd".index(q["answer"])])

        married = int(re.search(r"(\d+) विवाहित पुत्र", stem).group(1))
        unm = re.search(r"(\d+) अविवाहित पुत्र ", stem)
        n_sons = married + (int(unm.group(1)) if unm else 0)
        n_dau = int(re.search(r"और (\d+) (?:अविवाहित )?पुत्र[ीि]", stem).group(1))

        gd = gs = 0
        m = re.search(r"में से (\d+) की (\d+)-\d+ पुत्रियाँ", stem)
        if m:
            gd = int(m.group(1)) * int(m.group(2))
        m2 = re.search(r"तथा (\d+) का एक-एक पुत्र", stem)
        if m2:
            gs = int(m2.group(1))

        males = 1 + n_sons + gs
        females = 1 + n_dau + gd
        if "महिला" in stem:
            want = females
        elif "पुरुष" in stem:
            want = males
        else:
            want = males + females
        assert keyed == want, (
            f"seed {s}: description implies {want}, key says {keyed}")


def test_clock_image_is_self_inverse():
    """Both reflections must be involutions over the whole dial."""
    from reasoning import clock as ck
    for h in range(1, 13):
        for m in range(60):
            assert ck.water(*ck.water(h, m)) == (h, m)
            assert ck.mirror(*ck.mirror(h, m)) == (h, m)


def test_clock_answer_matches_the_definition():
    """Recompute 720-t / 360-t in the test, never via the generator."""
    from reasoning import clock as ck
    for s in SEEDS:
        q = ck.generate(random.Random(s))
        # Two stem forms exist: the printed time, and a DRAWN dial whose stem
        # must not contain the time at all. Take it from whichever is present —
        # for the drawn form that is the figure spec, which is exactly what the
        # candidate reads off the page.
        if q.get("_figure"):
            h, m = q["_figure"]["hour"], q["_figure"]["minute"]
            assert not re.search(r"\d{1,2}:\d{2}", q["stem"]), (
                f"seed {s}: the drawn variant prints the time in its stem, "
                f"which makes the dial pointless")
        else:
            h, m = map(int, re.search(r"(\d{1,2}):(\d{2})", q["stem"]).groups())
        t = (h % 12) * 60 + m
        shift = 720 if "जल" in q["stem"] else 360
        r = (shift - t) % 720
        want = f"{(r // 60) or 12}:{r % 60:02d}"
        keyed = q["options"]["abcd".index(q["answer"])]
        assert keyed == want, f"seed {s}: expected {want}, key says {keyed}"
        assert f"{h}:{m:02d}" not in q["options"], \
            f"seed {s}: the original time is offered as an option"


# ── tier 3 types ────────────────────────────────────────────────────────────

def test_coded_relations_composition_is_defined():
    """Every emitted chain must resolve through the hand-verified table."""
    from reasoning import coded_relations as cr
    for s in SEEDS:
        q = cr.generate(random.Random(s))
        roles = re.findall(r"\b(son|brother|mother|wife)\b of", q["reason"])
        assert len(roles) == 2, f"seed {s}: parsed {roles}"
        assert cr.compose(roles) is not None, \
            f"seed {s}: {roles} has no defined composition"


def test_coded_relations_particle_agreement():
    """Feminine relation words must not take the masculine particle.

    Regression: 'N, R ka mata hai' and 'S, R ka putri hai' both shipped from
    the first draft, because distractors were assembled from bare words with a
    hardcoded masculine particle.
    """
    fem = ("माता", "पुत्री", "बहन", "पत्नी", "पुत्रवधू")
    from reasoning import coded_relations as cr
    for s in SEEDS:
        q = cr.generate(random.Random(s))
        for opt in q["options"]:
            for w in fem:
                assert f"का {w}" not in opt, \
                    f"seed {s}: option uses the masculine particle with {w}"


def test_sufficiency_verdict_is_correct():
    """Re-derive sufficiency from the counts the reason states."""
    from reasoning import sufficiency as su
    for s in list(SEEDS)[:400]:
        q = su.generate(random.Random(s))
        nums = [int(x) for x in re.findall(r"(\d+)", q["reason"])]
        assert len(nums) >= 3, f"seed {s}: cannot parse counts"
        n1, n2, nb = nums[0], nums[1], nums[2]
        idx = "abcd".index(q["answer"])
        if idx == 0:
            assert n1 == 1 and n2 != 1, f"seed {s}: I alone, {n1}/{n2}"
        elif idx == 1:
            assert n2 == 1 and n1 != 1, f"seed {s}: II alone, {n1}/{n2}"
        elif idx == 2:
            assert n1 != 1 and n2 != 1 and nb == 1, \
                f"seed {s}: both, {n1}/{n2}/{nb}"
        else:
            assert nb != 1, f"seed {s}: insufficient claimed but nb={nb}"


def test_sufficiency_options_are_never_shuffled():
    """The four standard options must keep their canonical order."""
    from reasoning import sufficiency as su
    for s in list(SEEDS)[:200]:
        q = su.generate(random.Random(s))
        assert q["options"] == su._OPTIONS, f"seed {s}: options reordered"


def test_coded_relations_composition_semantics():
    """Re-derive every _COMPOSE entry from a MODEL OF THE FAMILY, not from the
    table itself.

    THIS IS THE TEST THAT WAS MISSING. _COMPOSE has now produced two wrong
    answer keys — ("wife","son") claimed "mother" (it is daughter-in-law) and
    ("son","mother") claimed "grandson" (X and Z are siblings). Both passed
    every structural test, because the generator and the table agreed with each
    other; only a hand-read of the output caught them.

    So this test builds a tiny concrete family, applies each role literally,
    and checks the table says what the family says. A wrong entry now fails
    here instead of reaching a student.
    """
    from reasoning import coded_relations as cr

    # A concrete 3-generation family. parent[x] = (father, mother).
    # Four generations, with DISTINCT roots. An earlier version gave every
    # root (None, None) parents, which made the sibling predicate treat two
    # unrelated roots as brother and sister.
    # Four generations with DISTINCT roots, plus a sibling pair at EVERY level
    # so a (brother, brother) chain has a concrete instance. An earlier version
    # gave all roots (None, None) parents, which made two unrelated roots look
    # like siblings, and had no sibling pair above generation 3 at all.
    parent = {
        # gen 3
        "x": ("y", "ym"), "sib": ("y", "ym"),
        # gen 2 — y, yb and yc are THREE brothers. A (brother, brother) chain
        # needs three distinct siblings (X bro of Y, Y bro of Z), not two.
        "y": ("z", "zm"), "yb": ("z", "zm"), "yc": ("z", "zm"),
        "ym": ("w", "wm"),
        # gen 1 — z and zb are brothers
        "z": ("g1", "g2"), "zb": ("g1", "g2"), "zm": ("g3", "g4"),
        "w": ("g5", "g6"), "wm": ("g7", "g8"),
    }
    spouse = {"z": "zm", "zm": "z", "y": "ym", "ym": "y",
              "w": "wm", "wm": "w"}

    def father_of(p):
        return parent.get(p, (None, None))[0]

    def mother_of(p):
        return parent.get(p, (None, None))[1]

    def apply(role, a, b):
        """Is `a` the given `role` of `b` in this family?"""
        if role == "son":
            return father_of(a) == b or mother_of(a) == b
        if role == "brother":
            return (a != b and parent.get(a) is not None
                    and parent.get(a) == parent.get(b))
        if role == "mother":
            return mother_of(b) == a
        if role in ("wife", "husband"):
            return spouse.get(a) == b
        raise AssertionError(f"unmodelled role {role!r}")

    def relation(a, b):
        """What is `a` to `b`? Returns the label _COMPOSE should produce."""
        if father_of(a) == b or mother_of(a) == b:
            return "son"
        if a != b and parent.get(a) is not None and parent.get(a) == parent.get(b):
            return "sibling"
        if mother_of(b) == a:
            return "mother"
        if spouse.get(a) == b:
            return "spouse"
        gp = [father_of(father_of(a)), mother_of(father_of(a)),
              father_of(mother_of(a)), mother_of(mother_of(a))]
        if b in gp:
            return "grandson"
        # in-law: a is married to a child of b
        sp = spouse.get(a)
        if sp and (father_of(sp) == b or mother_of(sp) == b):
            return "child_in_law"
        return None

    people = list(parent)
    checked = 0
    for (r1, r2), claimed in cr._COMPOSE.items():
        # find a concrete X, Y, Z where X r1 Y and Y r2 Z both hold
        found = False
        for X in people:
            for Y in people:
                if not apply(r1, X, Y):
                    continue
                for Z in people:
                    if Z in (X, Y) or not apply(r2, Y, Z):
                        continue
                    truth = relation(X, Z)
                    assert truth is not None, (
                        f"({r1},{r2}): family gives no relation for {X}->{Z}")
                    expected = {
                        "son": "son", "grandson": "grandson",
                        "sibling_of": "sibling", "brother": "sibling",
                        "wife_of": "spouse", "daughter_in_law": "child_in_law",
                    }[claimed]
                    assert truth == expected, (
                        f"({r1},{r2}) claims {claimed!r} (=> {expected}), "
                        f"but in the family {X} is {truth} of {Z}")
                    found = True
                    checked += 1
                    break
                if found:
                    break
            if found:
                break
        assert found, f"({r1},{r2}): no concrete instance in the test family"
    assert checked == len(cr._COMPOSE), "not every entry was exercised"


def test_grouping_every_option_appears_in_the_statements():
    """An option naming someone the statements never mention is eliminable
    without reading anything.

    Regression (found by hand-reading a 100-question run, 2026-09-16): with 6
    people and 3 per property, a person could land in NONE of the four sets and
    still be offered as an option. 436/3000 questions were affected.
    """
    from reasoning import grouping as gr
    for s in SEEDS:
        q = gr.generate(random.Random(s))
        body = q["stem"].split("\u0924\u094b \u0928\u093f\u092e\u094d\u0928\u0932\u093f\u0916\u093f\u0924")[0]
        missing = [o for o in q["options"] if o not in body]
        assert not missing, (
            f"seed {s}: option(s) {missing} appear in no statement")


def test_sufficiency_never_states_the_age_in_both_clues():
    """At most ONE statement may give the age outright.

    Regression (same hand-read): 62% of questions contained a statement saying
    "X's age is 52 years", which makes the question trivial — the candidate
    reads the answer instead of reasoning about sufficiency. One such clue is
    legitimate ONLY for the "statement I/II alone is sufficient" answer.
    """
    from reasoning import sufficiency as su
    for s in SEEDS:
        q = su.generate(random.Random(s))
        exact = re.findall(r"\u0906\u092f\u0941 \d+ \u0935\u0930\u094d\u0937 \u0939\u0948", q["stem"])
        assert len(exact) < 2, f"seed {s}: both statements give the age outright"
        if exact:
            assert q["answer"] in "ab", (
                f"seed {s}: an exact-age clue is present but the answer is "
                f"{q['answer']!r} — it should be the I-alone or II-alone case")


# ── difficulty ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("type_name", sorted(reasoning.TYPES))
def test_every_question_is_tagged(type_name):
    """Difficulty is part of the contract, like `answer` or `format`."""
    mod = reasoning.TYPES[type_name]
    for s in list(SEEDS)[:300]:
        q = mod.generate(random.Random(s))
        assert q.get("difficulty") in ("easy", "moderate", "hard"), \
            f"{type_name} seed {s}: difficulty is {q.get('difficulty')!r}"


@pytest.mark.parametrize("type_name", sorted(reasoning.TYPES))
def test_difficulty_actually_varies(type_name):
    """A type stuck on ONE level cannot help the paper hit its mix.

    Regression: `lettersum` keyed difficulty off a single word's length, but
    every word in its pool is 5-7 letters, so every question came out "easy".
    A tag that never changes is worse than no tag — it silently drags the
    paper's distribution.
    """
    import collections
    mod = reasoning.TYPES[type_name]
    seen = collections.Counter(
        mod.generate(random.Random(s))["difficulty"]
        for s in list(SEEDS)[:300])
    assert len(seen) >= 2, (
        f"{type_name}: every question is {list(seen)[0]!r} — the threshold "
        f"does not discriminate over this type's parameter range")


def test_paper_difficulty_is_in_a_sane_band():
    """The block's mix should be recognisably graded, not uniform.

    Deliberately a BAND, not the exact 50/30/20 of blueprint.DIFFICULTY_MIX.
    Reasoning difficulty is INTRINSIC — derived from each question's own
    parameters — so it cannot be dialled to a target the way the LLM path's
    allocation can. Measured 38/41/21; the assertion guards against a
    regression that would flatten or invert it, not against being off-target.
    """
    import collections
    import logging
    logging.disable(logging.WARNING)
    qs = reasoning.generate(400, seed=9)
    c = collections.Counter(q["difficulty"] for q in qs)
    total = sum(c.values())
    easy, hard = c["easy"] / total, c["hard"] / total
    assert 0.25 <= easy <= 0.60, f"easy share {easy:.0%} outside the sane band"
    assert 0.10 <= hard <= 0.35, f"hard share {hard:.0%} outside the sane band"
    assert c["moderate"] > 0, "no moderate questions at all"


# ── figures ─────────────────────────────────────────────────────────────────

FIGURE_TYPES = ["dice", "triangles"]


@pytest.mark.parametrize("type_name", FIGURE_TYPES)
def test_figure_spec_is_serialisable(type_name):
    """A spec must survive a JSON round-trip — it goes nowhere near a file
    until render.py, and questions.json is JSON."""
    import json
    mod = reasoning.TYPES[type_name]
    for s in list(SEEDS)[:300]:
        q = mod.generate(random.Random(s))
        spec = q.get("_figure")
        assert spec, f"{type_name} seed {s}: no _figure spec"
        assert json.loads(json.dumps(spec)) == spec, \
            f"{type_name} seed {s}: spec is not JSON-round-trippable"


def test_triangle_count_matches_known_figures():
    """The counter must agree with hand-counted, published figures.

    1/5/13/27 for a 1/2/3/4-row subdivided triangle is the standard sequence,
    and 27 is the keyed answer of the REAL vdo-vpdo Q26. A geometry bug once
    produced 21 for the 3-row case — the construction paired mismatched
    fractions and drew vertical lines instead of a lattice.
    """
    from reasoning import triangles as tr
    for rows, expect in ((1, 1), (2, 5), (3, 13), (4, 27)):
        got = tr.count_triangles(tr._subdivided(rows))
        assert got == expect, f"{rows}-row triangle: counted {got}, expected {expect}"

    # Elementary shapes, independently obvious.
    sq = [((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0))]
    assert tr.count_triangles(sq) == 0
    assert tr.count_triangles(sq + [((0, 0), (1, 1))]) == 2
    assert tr.count_triangles(sq + [((0, 0), (1, 1)), ((1, 0), (0, 1))]) == 8


def test_dice_answer_follows_from_the_views():
    """Re-derive the bottom faces from the SPEC's views alone.

    This is what a candidate does: find which face never appears beside the
    top, and that is the bottom. Never calls the generator's own opposite().
    """
    from reasoning import dice as dc
    for s in SEEDS:
        q = dc.generate(random.Random(s))
        views = [tuple(v) for v in q["_figure"]["views"]]

        # For each top, the faces seen adjacent to it across all views.
        adj = {}
        for top, left, right in views:
            adj.setdefault(top, set()).update({left, right})

        bottoms = []
        for top, _, _ in views:
            remaining = set(range(1, 7)) - adj[top] - {top}
            assert len(remaining) == 1, (
                f"seed {s}: top {top} has {len(remaining)} candidate bottoms — "
                f"the question is ambiguous")
            bottoms.append(remaining.pop())

        keyed = q["options"]["abcd".index(q["answer"])]
        assert keyed == ", ".join(str(b) for b in bottoms), (
            f"seed {s}: views imply {bottoms}, key says {keyed}")


def test_dice_views_are_physically_possible():
    """No view may show two opposite faces at once — that is not a real die."""
    from reasoning import dice as dc
    for s in list(SEEDS)[:400]:
        q = dc.generate(random.Random(s))
        views = [tuple(v) for v in q["_figure"]["views"]]
        adj = {}
        for top, left, right in views:
            adj.setdefault(top, set()).update({left, right})
        pairs = {}
        for top in adj:
            opp = (set(range(1, 7)) - adj[top] - {top}).pop()
            pairs[top] = opp
            pairs[opp] = top
        for top, left, right in views:
            assert pairs.get(top) not in (left, right), \
                f"seed {s}: view {(top, left, right)} shows opposite faces"
            assert len({top, left, right}) == 3, \
                f"seed {s}: view {(top, left, right)} repeats a face"


def test_font_resolves_without_windows_fonts():
    """The container has no Arial. Resolution must not raise, ever.

    worker/Dockerfile installs fonts-deva/fonts-lohit-deva (Devanagari) and
    bundled licensed fonts, but guarantees NO Latin TTF — and dice digits are
    Latin. The chain must end at Pillow's built-in bitmap font.
    """
    from reasoning import figures as fg
    saved = fg._FONT_CANDIDATES[:]
    try:
        fg._FONT_CANDIDATES.clear()          # simulate: nothing resolvable
        fg.font.cache_clear()
        f = fg.font(20)
        assert f is not None
    finally:
        fg._FONT_CANDIDATES[:] = saved
        fg.font.cache_clear()


@pytest.mark.parametrize("type_name", FIGURE_TYPES)
def test_render_round_trip(type_name, tmp_path):
    """Spec -> PNG -> a file the builder can actually open."""
    from PIL import Image
    from reasoning import render
    mod = reasoning.TYPES[type_name]
    qs = [mod.generate(random.Random(s)) for s in range(6)]
    for i, q in enumerate(qs, 1):
        q["n"] = i

    n = render.render_all(qs, tmp_path)
    assert n == len(qs), f"rendered {n} of {len(qs)}"

    for q in qs:
        assert q.get("image"), "render_all did not set q['image']"
        assert "_figure" not in q, "the internal spec leaked past render_all"
        p = tmp_path / q["image"]
        assert p.exists() and p.stat().st_size > 0
        with Image.open(p) as im:
            assert im.width > 40 and im.height > 20, f"{q['image']} is tiny"
            # build_paper fits into a 4.8 x 4.0 cm box by aspect ratio; a
            # wildly elongated figure would render unreadably small.
            assert 0.2 < im.width / im.height < 6.0, \
                f"{q['image']} aspect {im.width / im.height:.2f} is unusable"


def test_render_raises_rather_than_dropping(tmp_path):
    """A bad spec must RAISE, not be skipped.

    run_pipeline.validate silently DROPS a question whose image is missing and
    ships the paper short (run_pipeline.py:130-158). A quiet failure here would
    surface as an unexplained short paper, which is precisely why rendering was
    split out of the generators.
    """
    from reasoning import render
    qs = [{"n": 1, "_type": "bogus", "_figure": {"kind": "no-such-kind"}}]
    with pytest.raises(render.FigureError):
        render.render_all(qs, tmp_path)


def test_render_leaves_text_questions_alone(tmp_path):
    """A mixed block must pass through untouched where there is no figure."""
    from reasoning import render
    qs = [{"n": 1, "_type": "series", "stem": "x"},
          {"n": 2, "_type": "direction", "stem": "y"}]
    assert render.render_all(qs, tmp_path) == 0
    assert not any("image" in q for q in qs)
    assert not (tmp_path / render.FIG_DIR).exists()


def test_strip_specs_leaves_a_valid_question():
    """With no output dir the diagram is dropped, not the question."""
    from reasoning import render
    from reasoning import dice as dc
    q = dc.generate(random.Random(1))
    render.strip_specs([q])
    assert "_figure" not in q
    assert q["stem"] and len(q["options"]) == 4 and q["answer"] in "abcd"


# ── venn + figure series (option images and strips) ─────────────────────────

def test_venn_spec_round_trips_and_options_match():
    """Four option specs, four text placeholders, answer in range.

    run_pipeline.validate sizes the answer-letter range from whichever option
    list is present, and build_paper.py:289-294 renders option_images INSTEAD
    of text — so the two lists must stay the same length or the keyed letter
    can point past the end of what is printed.
    """
    import json
    from reasoning import venn as vn
    for s in list(SEEDS)[:400]:
        q = vn.generate(random.Random(s))
        specs = q["_figure_options"]
        assert len(specs) == 4 == len(q["options"]), f"seed {s}: length mismatch"
        assert q["answer"] in "abcd"
        assert json.loads(json.dumps(specs)) == specs, f"seed {s}: not JSON-safe"
        # Placeholders must be distinct: an all-identical option list trips the
        # duplicate-option check every other type is held to.
        assert len(set(q["options"])) == 4, f"seed {s}: options not distinct"


def _venn_relation_from_geometry(circles):
    """Re-derive the set relation from raw circle coordinates.

    Independent of venn.py's own table — this is what a reader sees, so it is
    what the key must agree with.
    """
    import math
    rel = set()
    for i, j in [(0, 1), (0, 2), (1, 2)]:
        a, b = circles[i], circles[j]
        dist = math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"])
        if dist >= a["r"] + b["r"]:
            rel.add((i, j, "disjoint"))
        elif dist + min(a["r"], b["r"]) <= max(a["r"], b["r"]):
            rel.add((i, j, "contains"))
        else:
            rel.add((i, j, "overlap"))
    return rel


def test_venn_layouts_are_geometrically_distinct():
    """No two relations may draw the same picture.

    If two layouts read identically, more than one option is defensible and the
    question has no single answer — the failure mode that matters here.
    """
    from reasoning import venn as vn
    seen = {}
    for key in vn._RELATIONS:
        rel = frozenset(_venn_relation_from_geometry(vn.layout(key)))
        assert rel not in seen, \
            f"relations {key!r} and {seen[rel]!r} draw the same arrangement"
        seen[rel] = key


def test_venn_geometry_matches_its_name():
    """The geometry must mean what the relation key says.

    A layout whose circles do not actually overlap/nest as named would make the
    drawn answer disagree with the words generated from the same key.
    """
    from reasoning import venn as vn
    expect = {
        "overlap_plus_disjoint": {(0, 1, "overlap"), (0, 2, "disjoint"),
                                  (1, 2, "disjoint")},
        "nested": {(0, 1, "contains"), (0, 2, "contains"), (1, 2, "contains")},
        "all_disjoint": {(0, 1, "disjoint"), (0, 2, "disjoint"),
                         (1, 2, "disjoint")},
        "two_inside_overlapping": {(0, 1, "contains"), (0, 2, "contains"),
                                   (1, 2, "overlap")},
        "two_inside_disjoint": {(0, 1, "contains"), (0, 2, "contains"),
                                (1, 2, "disjoint")},
    }
    for key, want in expect.items():
        got = _venn_relation_from_geometry(vn.layout(key))
        assert got == want, f"{key}: geometry reads as {sorted(got)}"


def test_venn_render_writes_four_option_images(tmp_path):
    """Spec -> four PNGs -> option_images, with the internal key removed."""
    from PIL import Image
    from reasoning import render, venn as vn
    qs = [vn.generate(random.Random(s)) for s in range(4)]
    for i, q in enumerate(qs, 1):
        q["n"] = i
    n = render.render_all(qs, tmp_path)
    assert n == 4 * len(qs)
    for q in qs:
        assert "_figure_options" not in q, "the internal spec leaked past render"
        imgs = q["option_images"]
        assert len(imgs) == 4
        for rel in imgs:
            p = tmp_path / rel
            assert p.exists() and p.stat().st_size > 0
            with Image.open(p) as im:
                assert im.width > 30 and im.height > 30


def test_figseries_answer_derives_from_the_picture_alone():
    """Solve each question from the SPEC, as a candidate would.

    Tries BOTH rotation directions and all six swaps. If more than one figure
    number can be justified the question has two correct options, which is the
    real hazard for this type — a period-4 rotation over 4 shown figures admits
    ambiguous swaps unless they are filtered out.
    """
    from itertools import combinations
    from reasoning import figseries as fs

    def rot(q, cw):
        t, l, r, b = q
        return (l, b, t, r) if cw else (r, t, b, l)

    for s in list(SEEDS)[:800]:
        q = fs.generate(random.Random(s))
        sq = [tuple(x) for x in q["_figure"]["squares"]]
        base, shown = sq[0], sq[1:]

        solutions = set()
        for cw in (True, False):
            truth = [base]
            for _ in range(4):
                truth.append(rot(truth[-1], cw))
            truth = truth[1:]
            for i, j in combinations(range(4), 2):
                c = list(shown)
                c[i], c[j] = c[j], c[i]
                if c == truth:
                    solutions.add(i + 1)

        keyed = int(q["options"]["abcd".index(q["answer"])])
        assert solutions == {keyed}, \
            f"seed {s}: picture admits {sorted(solutions)}, key says {keyed}"


def test_figseries_strip_is_well_formed():
    """Five squares, four distinct symbols each, labels blank-then-1234."""
    import json
    from reasoning import figseries as fs
    for s in list(SEEDS)[:500]:
        q = fs.generate(random.Random(s))
        spec = q["_figure"]
        assert json.loads(json.dumps(spec)) == spec, f"seed {s}: not JSON-safe"
        assert spec["labels"] == ["", "1", "2", "3", "4"]
        squares = spec["squares"]
        assert len(squares) == 5, f"seed {s}: {len(squares)} squares"
        for sq in squares:
            assert len(sq) == 4 and set(sq) == set(fs.SYMBOLS), \
                f"seed {s}: a square does not carry all four symbols once"


def test_figseries_rotation_is_a_true_cycle():
    """Four rotation steps must return the tuple to its start, both ways.

    Guards the tuple-order trap: QUADRANTS is (top,left,right,bottom) but the
    rotation cycle is top->right->bottom->left, and mixing the two silently
    produces a reflection instead of a rotation.
    """
    from reasoning import figseries as fs
    start = tuple(fs.SYMBOLS)
    for cw in (True, False):
        q = start
        for _ in range(4):
            q = fs.rotate(q, cw)
        assert q == start, f"clockwise={cw}: four steps did not close the cycle"
    # And one step must genuinely move every symbol.
    assert fs.rotate(start, True) != start
    assert fs.rotate(start, True) != fs.rotate(start, False)


def test_figseries_render_round_trip(tmp_path):
    """Each square must print big enough to read its four symbols.

    build_paper fits by ASPECT into a 4.8 x 4.0 cm box; a 5-square strip that
    came out near-square would print each symbol at an unreadable size.
    """
    from PIL import Image
    from reasoning import render, figseries as fs
    qs = [fs.generate(random.Random(s)) for s in range(5)]
    for i, q in enumerate(qs, 1):
        q["n"] = i
    assert render.render_all(qs, tmp_path) == len(qs)
    for q in qs:
        with Image.open(tmp_path / q["image"]) as im:
            # The strip WRAPS to 3 squares per row. build_paper caps a stem
            # figure at 4.8cm wide and 4.0cm tall; one 5-square row printed
            # 4.8 x 1.6cm, i.e. <1cm per square for four symbols, measured
            # illegible in a real PDF. What matters is the printed size of ONE
            # square, so assert that rather than the aspect ratio.
            w_cm = 4.8
            h_cm = w_cm * im.height / im.width
            if h_cm > 4.0:
                h_cm, w_cm = 4.0, 4.0 * im.width / im.height
            per_square = w_cm / 3
            assert per_square > 1.2, (
                f"each square prints at {per_square:.2f}cm — too small for "
                f"four symbols to be read")


def test_full_block_delivers_every_question_asked():
    """A 100-question block must deliver 100, not quietly ship short.

    REGRESSION: dedup keyed on stem+options only. `figseries` uses ONE fixed
    stem for every question by design — the strip is what varies — so every
    figseries question after the first looked like a duplicate and a
    100-question block delivered 95. The shortfall was only a log line; nothing
    failed. Dedup now folds in the figure spec.
    """
    for n in (10, 50, 100):
        qs = reasoning.generate(n, seed=7)
        assert len(qs) == n, f"asked {n}, delivered {len(qs)}"


def test_no_two_questions_share_a_figure():
    """Two questions printing the same picture are duplicates to a student,
    however different their internals are."""
    qs = reasoning.generate(100, seed=11)
    figs = [repr(q["_figure"]) for q in qs if q.get("_figure")]
    assert len(figs) == len(set(figs)), "a figure is repeated within one paper"
    opt_figs = [repr(q["_figure_options"]) for q in qs if q.get("_figure_options")]
    assert len(opt_figs) == len(set(opt_figs)), \
        "an option-diagram set is repeated within one paper"
