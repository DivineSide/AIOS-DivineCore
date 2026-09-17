# -*- coding: utf-8 -*-
"""Split general-gk's 24 bullets into per-discipline subject files.

NOT a re-authoring: the bullets, facets and leaves are the SAME objects, just
grouped by the syllabus section they already came from (2.2 history, 2.3
geography, 2.4 polity, 2.5 economics, 2.6 evergreen GK). general-gk.json stays
untouched and complete, because EXAM mode still allocates against it as one
measured bucket.
"""
import json, pathlib

# Resolved against THIS file, not the cwd — the script is a re-derivation tool
# that has to work from anywhere, including a CI checkout.
D = pathlib.Path(__file__).resolve().parent / 'uksssc-master'
src = json.loads((D / 'general-gk.json').read_text(encoding='utf-8'))
bullets = src["bullets"]

# Bullet index ranges per syllabus section, 0-based, end-exclusive.
# Derived from syllabus.py's own section comments (2.2/2.3/2.4/2.5/2.6).
SPLIT = {
    "indian-history":   (0, 4,   "UKSSSC master syllabus 2026-08-31, 2.2 इतिहास"),
    "indian-geography": (4, 11,  "UKSSSC master syllabus 2026-08-31, 2.3 भूगोल"),
    "indian-polity":    (11, 15, "UKSSSC master syllabus 2026-08-31, 2.4 राजनीति विज्ञान"),
    "indian-economics": (15, 22, "UKSSSC master syllabus 2026-08-31, 2.5 अर्थशास्त्र"),
}

NOTE = ("Carved out of general-gk.json by syllabus section — the SAME authored "
        "bullets/facets/leaves, regrouped so a teacher can order one discipline. "
        "general-gk.json remains complete and unchanged: EXAM mode still "
        "allocates against it as a single measured bucket (its 0.22-0.30 share "
        "was counted from real papers at the general-gk level, never per "
        "discipline). Do not re-author here — edit general-gk.json and re-run "
        "the split, or the two drift apart.")

for subject, (lo, hi, source) in SPLIT.items():
    part = bullets[lo:hi]
    doc = {
        "subject": subject,
        "syllabus_source": source,
        "authored": src.get("authored"),
        "note": NOTE,
        "bullets": part,
    }
    p = D / f"{subject}.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
    n = sum(len(f["leaves"]) for b in part for f in b["facets"])
    print(f"{subject:18s} {len(part):2d} bullets  {n:3d} leaves -> {p.name}")

covered = sum(hi - lo for lo, hi, _ in SPLIT.values())
print(f"\nbullets 1-{covered} split; bullets {covered+1}-{len(bullets)} "
      f"(evergreen GK) stay ONLY in general-gk.json")
