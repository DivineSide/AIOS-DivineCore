"""
Generate partitioned Apify input JSON files to pull FRESH leads across runs.

The actor returns the same top matches when given the same filter. To get
non-overlapping leads, we partition the search space on two axes:
  1. Employee size group  — a company is in exactly ONE bucket (clean non-overlap)
  2. Keyword theme        — different product emphasis surfaces different brands

size_groups (3) x keyword_themes (3) = 9 distinct filter combos.

Reads exclusions/titles/industries/locations from the ICP's scrape.yaml so
those stay in sync. Only the partitioning axes are defined here.

Usage:
  python workflows/scrape/gen-batch-inputs.py ecommerce-uk --client divinecore [--count 100]

Output: scrape-inputs/<icp>/<icp>_<sizegroup>_<theme>.json
Paste each into the Apify actor UI and run. Then fetch all outputs and filter
together (dedup handles any residual overlap).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

SIZE_GROUPS = {
    "micro": ["1-10", "11-20"],
    "small": ["21-50", "51-100"],
    "mid":   ["101-200", "201-500"],
}

# Keyword themes — each is a subset of include_any in scrape.yaml.
# Edit here when you change the ICP's keyword strategy.
KEYWORD_THEMES = {
    "core":    ["skincare", "skin care", "serum", "moisturiser", "moisturizer",
                "cleanser", "retinol", "face cream", "eye cream"],
    "sunbody": ["spf", "sunscreen", "body care", "lip care", "beauty brand", "cosmetics"],
    "natural": ["natural beauty", "clean beauty", "organic skincare", "vegan skincare",
                "vegan beauty", "cruelty free", "cruelty-free", "dtc beauty"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("icp")
    ap.add_argument("--client", required=True)
    ap.add_argument("--count", type=int, default=100)
    args = ap.parse_args()

    cfg_path = ROOT / "Clients" / args.client / "icps" / args.icp / "scrape.yaml"
    if not cfg_path.exists():
        print(f"ERROR: scrape config not found at {cfg_path}")
        sys.exit(1)

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    f = cfg["filters"]

    chains = cfg.get("exclude_companies", {}).get("chains") or []
    not_keywords = list(f["company_keywords"].get("exclude_any", [])) + chains

    # Validate themes are subsets of the ICP's include_any (warn on drift)
    include_any = set(f["company_keywords"]["include_any"])
    for theme, kws in KEYWORD_THEMES.items():
        missing = [k for k in kws if k not in include_any]
        if missing:
            print(f"WARNING: theme '{theme}' has keywords not in scrape.yaml include_any: {missing}")

    out_dir = ROOT / "scrape-inputs" / args.icp
    out_dir.mkdir(parents=True, exist_ok=True)

    base = {
        "contact_job_title": f["titles"]["include"],
        "contact_not_job_title": f["titles"]["exclude"],
        "seniority_level": cfg.get("seniority_level", ["founder", "owner", "c_suite"]),
        "contact_location": f["locations"],
        "company_industry": f["industries"]["include"],
        "company_not_keywords": not_keywords,
        "email_status": ["validated"],
    }

    written = []
    for size_name, sizes in SIZE_GROUPS.items():
        for theme_name, keywords in KEYWORD_THEMES.items():
            label = f"{args.icp}_{size_name}_{theme_name}"
            payload = {
                "fetch_count": args.count,
                "file_name": label,
                **base,
                "size": sizes,
                "company_keywords": keywords,
            }
            path = out_dir / f"{label}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(path.name)

    print(f"Generated {len(written)} input files in {out_dir}\n")
    for name in written:
        print(f"  {name}")
    print(f"\nRun each in the Apify UI, save outputs to data/, then filter all together:")
    print(f"  python workflows/scrape/filter-leads-us.py {args.icp} --client {args.client} data/*.json --out data/{args.icp}-final.json")


if __name__ == "__main__":
    main()
