# -*- coding: utf-8 -*-
"""calendar_year — calendar-repetition questions, correct by construction.

MODELLED ON: vdo-vpdo 2023-12-31 Q98 —

    वर्ष 2009 का कैलेण्डर ____ वर्ष के समान है ।
    (A) 2013 (B) 2014 (C) 2015 (D) 2016            -> answer 2015

VERIFIED INDEPENDENTLY before building: from 2009 to 2015 the cumulative day
count is ≡ 0 (mod 7) AND both are non-leap, so the calendars coincide. 2013 is
5 days off, 2014 is 6, and 2016 is a leap year so it can never match a non-leap
year regardless of shift. The key is sound — unlike Q91's, which is why this
type is modelled on the source and the clock type is not.

THE RULE, in full: two years share a calendar iff
  (a) the days between them are a whole number of weeks, and
  (b) they have the SAME leap status.
Condition (b) is the one candidates forget, and it is why the naive "add 6 or
11 years" shortcut fails across century boundaries.

Interface:
    generate(rng)                -> question dict
    is_leap(y)                   -> bool      # pure, for tests
    next_same_calendar(y)        -> int       # pure, for tests
"""
from __future__ import annotations

import random

from . import pools  # noqa: F401  (kept for the shared-vocabulary convention)
from .util import distinct_wrongs, finish

# Range the questions draw from. Chosen to stay inside the Gregorian rules a
# candidate is taught (no pre-1752 reform weirdness) and near enough to now
# that the years read as plausible exam content.
_YEAR_MIN, _YEAR_MAX = 1990, 2040

# Several phrasings — a fixed stem makes two of this type in one paper read as
# duplicates even though the years differ (caught by the block-distinctness
# test when this type was registered).
_STEMS = [
    "वर्ष {y} का कैलेण्डर निम्नलिखित में से किस वर्ष के समान होगा ?",
    "निम्नलिखित में से किस वर्ष का कैलेण्डर वर्ष {y} के कैलेण्डर जैसा ही होगा ?",
    "वर्ष {y} के बाद वही कैलेण्डर किस वर्ष दोहराया जाएगा ?",
]


def is_leap(y: int) -> bool:
    """Gregorian leap year. O(1)."""
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_between(y1: int, y2: int) -> int:
    """Days from 1 Jan y1 to 1 Jan y2. O(y2 - y1)."""
    return sum(366 if is_leap(y) else 365 for y in range(y1, y2))


def next_same_calendar(y: int, after: int | None = None) -> int:
    """The first year after `y` whose calendar is identical.

    Identical means: whole weeks apart AND same leap status. Searches forward
    year by year — the gap is at most 28 (and usually 6 or 11), so the loop is
    bounded in practice; the hard cap is a guard, not an expectation.

    Independent of generate()'s construction path, for the tests.
    """
    start = after if after is not None else y
    shift = _days_between(y, start + 1) % 7
    cand = start + 1
    while cand < y + 100:
        if shift % 7 == 0 and is_leap(cand) == is_leap(y):
            return cand
        shift = (shift + (366 if is_leap(cand) else 365)) % 7
        cand += 1
    raise ValueError(f"no repeat found for {y}")     # pragma: no cover


def generate(rng: random.Random) -> dict:
    """One calendar-repetition question. O(gap) — at most ~28 iterations."""
    year = rng.randint(_YEAR_MIN, _YEAR_MAX)
    answer = next_same_calendar(year)

    # Distractors are the years a candidate lands on by a REAL error:
    #   - the years either side of the answer (off-by-one in the day count)
    #   - the year that IS a whole number of weeks away but has the wrong leap
    #     status — the single most common mistake, and the one the 2016 option
    #     in the source question is testing
    #   - the naive "+6" / "+11" shortcut applied blindly
    cands: list[int] = []
    for delta in (1, -1, 2):
        if year < answer + delta:
            cands.append(answer + delta)
    for c in range(year + 1, year + 30):
        if c == answer:
            continue
        if _days_between(year, c) % 7 == 0 and is_leap(c) != is_leap(year):
            cands.append(c)                 # right shift, wrong leap status
            break
    for shortcut in (year + 6, year + 11):
        if shortcut != answer:
            cands.append(shortcut)

    wrongs = distinct_wrongs(answer, cands, rng, n=3)
    opts, letter = finish(str(answer), [str(w) for w in wrongs], rng)

    gap = answer - year
    return {
        "stem": rng.choice(_STEMS).format(y=year),
        "options": opts,
        "answer": letter,
        "format": "plain",
        # Intrinsic: the common 6- and 11-year gaps are the taught cases;
        # anything else means the leap pattern had to be worked through.
        # The 6- and 11-year gaps are the taught shortcut; anything else
        # means the leap pattern had to be worked through properly.
        "difficulty": "easy" if gap == 6 else
                      "moderate" if gap == 11 else "hard",
        "reason": f"{year} और {answer} के बीच के दिनों की संख्या 7 का पूर्ण "
                  f"गुणज है तथा दोनों वर्ष "
                  f"{'अधिवर्ष' if is_leap(year) else 'सामान्य वर्ष'} हैं; "
                  f"अतः {gap} वर्ष बाद वही कैलेण्डर दोहराता है।",
        "_type": "calendar_year",
        "_dedup_key": f"calendar:{year}",
    }
