"""
Post-Scrape Filter (US pipeline) — removes noise that Apollo's exclude filters don't catch.

Reads one or more scrape JSON files, dedupes by email/company_domain,
applies blacklist/whitelist rules loaded from clients/<client>/icps/<icp>/qualify.yaml.

Three-layer filter architecture:
  1. name_blacklist     — checked against company name only
  2. desc_blacklist     — checked against company description (specific phrases only)
  3. keywords_blacklist — checked against Apollo keywords field (structured tags, high signal)
  4. name_whitelist     — name must contain an ICP signal

Usage:
  python execution/scrape/filter-leads-us.py <icp> --client <client> <input1.json> [input2.json ...] --out <output.json>
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]


def load_filter_rules(client: str, icp: str) -> dict:
    path = ROOT / "clients" / client / "icps" / icp / "qualify.yaml"
    if not path.exists():
        print(f"ERROR: qualify config not found at {path}")
        sys.exit(1)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = data.get("filter_rules", {})
    return {
        "name_blacklist": [t.lower() for t in rules.get("name_blacklist", [])],
        "desc_blacklist": [t.lower() for t in rules.get("desc_blacklist", [])],
        "keywords_blacklist": [t.lower() for t in rules.get("keywords_blacklist", [])],
        "name_whitelist": [t.lower() for t in rules.get("name_whitelist", [])],
    }


def load_leads(paths: list[Path]) -> list[dict]:
    seen = set()
    leads = []
    for p in paths:
        items = json.loads(p.read_text(encoding="utf-8"))
        for l in items:
            key = (l.get("email") or "").lower()
            if not key:
                key = f"{(l.get('company_domain') or '').lower()}|{(l.get('company_name') or '').lower()}"
            if key in seen:
                continue
            seen.add(key)
            leads.append(l)
    return leads


def qualify(lead: dict, rules: dict) -> tuple[bool, str]:
    name = (lead.get("company_name") or "").lower()
    desc = (lead.get("company_description") or "").lower()
    keywords = (lead.get("keywords") or "").lower()

    for term in rules["name_blacklist"]:
        if term in name:
            return False, f"blacklist:{term}"

    for term in rules["desc_blacklist"]:
        if term in desc:
            return False, f"desc_blacklist:{term}"

    for term in rules["keywords_blacklist"]:
        if term in keywords:
            return False, f"keywords_blacklist:{term}"

    whitelist = rules["name_whitelist"]
    if whitelist:
        passes_name = any(term in name for term in whitelist)
        passes_keywords = any(term in keywords for term in whitelist) if keywords else False
        if not (passes_name or passes_keywords):
            return False, "whitelist:no_icp_signal"

    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("icp")
    ap.add_argument("--client", required=True, help="Client folder name, e.g. acme-corp")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rules = load_filter_rules(args.client, args.icp)
    paths = [ROOT / p if not Path(p).is_absolute() else Path(p) for p in args.inputs]
    leads = load_leads(paths)

    kept, dropped = [], []
    for l in leads:
        ok, reason = qualify(l, rules)
        (kept if ok else dropped).append((l, reason))

    out_path = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    out_path.write_text(
        json.dumps([l for l, _ in kept], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Client:        {args.client}")
    print(f"ICP:           {args.icp}")
    print(f"Input total:   {len(leads)}")
    print(f"Kept:          {len(kept)}")
    print(f"Dropped:       {len(dropped)}")
    print()
    print("=== KEPT ===")
    for l, _ in kept:
        print(f"  {l.get('company_name'):<50} {l.get('country'):<15} {l.get('job_title')}")
    print()
    print("=== DROPPED ===")
    for l, r in dropped:
        print(f"  [{r}] {l.get('company_name'):<45} — {l.get('job_title')}")
    print()
    print(f"Match rate:    {len(kept)/len(leads)*100:.0f}%")
    print(f"Written to:    {out_path}")


if __name__ == "__main__":
    main()
