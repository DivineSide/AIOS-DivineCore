"""
CSV-driven personalization for the divinecore Marketing-OS cold-email campaign.

Reads an input CSV (the Apollo/Instantly leads export shape), filters to
verified leads, picks a template variant per row via a lightweight heuristic
on Founded Year (no website scraping -- fast path), rotates the seasonal
trigger library row-by-row for the {{opener_line}} substitution, and writes
an output CSV with the per-lead subject + first-touch body + second-touch
body filled in. Ready to upload to Instantly.

Usage (run from the divinecore-v2/ folder so paths resolve correctly):

    python sales_os/Clients/divinecore/personalize_from_csv.py \\
      --input  sales_os/Clients/divinecore/data/verified-leads-2026-05-28.csv \\
      --output sales_os/Clients/divinecore/data/verified-leads-2026-05-28-personalized.csv

Or just `--input` and `--output` will both default to the standard data/ paths.

Why no website scraping in v1:
  Mayank's canonical pipeline (enrich-leads-us.py) visits each lead's homepage
  to detect Meta pixel + product-launch keywords + brand age, then picks the
  template variant accordingly. That works but takes ~10-15s per lead. For
  300 leads that's ~45 min and many sites will rate-limit or block.
  This script trades that bespoke detection for speed: every lead gets the
  fallback template (Mayank's generic Marketing-OS pitch), with the opener
  line rotated through the 6 seasonal triggers in trigger-library.yaml so
  consecutive emails sent in the same campaign window don't look identical
  to mailbox providers. Add a v2 site-scrape pass later if conversion is weak.

Verification-status filter:
  Only rows where Verification Status == "Verified" are personalized. Rows
  flagged "Invalid" by the verifier are dropped (sending to invalid emails
  damages sending-domain reputation). The dropped count is printed at end.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml


CLIENT_DIR = Path(__file__).resolve().parent
TEMPLATES_PATH = CLIENT_DIR / "templates" / "ecommerce-uk-email.yaml"
TRIGGERS_PATH = CLIENT_DIR / "triggers" / "trigger-library.yaml"
DEFAULT_INPUT = CLIENT_DIR / "data" / "verified-leads-2026-05-28.csv"
DEFAULT_OUTPUT = CLIENT_DIR / "data" / "verified-leads-2026-05-28-personalized.csv"

ICP_KEY = "ecommerce-uk"


def load_templates(path: Path) -> dict[str, dict]:
    """Returns {signal_type: doc} from the multi-doc YAML template file."""
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for doc in yaml.safe_load_all(text):
        if isinstance(doc, dict) and "signal_type" in doc:
            out[doc["signal_type"]] = doc
    return out


def load_triggers(path: Path, icp: str) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_triggers = (data.get(icp) or {}).get("triggers") or []
    # Strip whitespace + collapse internal newlines so each trigger is one paragraph.
    cleaned: list[str] = []
    for t in raw_triggers:
        if not t:
            continue
        text = " ".join(str(t).split())
        cleaned.append(text)
    return cleaned


def pick_signal(founded_year_raw: str) -> str:
    """Cheap heuristic: brands founded 5+ years ago get the mature template,
    everyone else gets the fallback. This is the no-site-scrape path.
    Threshold: 2021 (i.e. 2026 - 5) -- brands from 2021 or earlier are 'mature'."""
    try:
        year = int(str(founded_year_raw).strip())
    except (TypeError, ValueError):
        return "fallback"
    if year and year <= 2021:
        return "mature_ad_account"
    return "fallback"


def render(template_text: str, first_name: str, company_name: str, opener_line: str) -> str:
    return (
        template_text
        .replace("{{first_name}}", first_name)
        .replace("{{company_name}}", company_name)
        .replace("{{opener_line}}", opener_line.strip())
    )


def clean_first_name(raw: str) -> str:
    """Pang doesn't write 'Hey ,' or 'Hey there' robotically. If first name
    is missing or weird, we leave it as-is and let the recipient see the
    awkwardness in QA -- or you spot-check and skip those rows pre-upload."""
    if not raw:
        return ""
    return raw.strip()


# Lowercase substrings that, if found in Company Address, mark the lead as UK.
# Conservative bias: if NONE of these match, we flag as non-UK. So an empty
# or weird address gets flagged too -- safer than false-negative for an
# outside-niche send.
UK_MARKERS = (
    ", gb",
    " gb,",
    "(gb)",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "great britain",
)


def is_non_uk(company_address: str) -> bool:
    """True if the company address has no recognizable UK marker. Flagged
    leads still get personalized -- the operator just sees them tagged in
    the CSV so they can drop or hand-edit before upload to Instantly."""
    if not company_address:
        return True
    addr = company_address.lower()
    return not any(marker in addr for marker in UK_MARKERS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"ERROR: input CSV not found at {in_path}", file=sys.stderr)
        sys.exit(1)

    templates = load_templates(TEMPLATES_PATH)
    triggers = load_triggers(TRIGGERS_PATH, ICP_KEY)
    if not triggers:
        print(f"ERROR: no triggers loaded for ICP '{ICP_KEY}' from {TRIGGERS_PATH}", file=sys.stderr)
        sys.exit(1)
    if "fallback" not in templates:
        print(f"ERROR: no 'fallback' signal_type in templates {TEMPLATES_PATH}", file=sys.stderr)
        sys.exit(1)

    with in_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print(f"ERROR: input CSV is empty: {in_path}", file=sys.stderr)
        sys.exit(1)

    # Filter to Verified only.
    invalid_dropped = sum(
        1 for r in rows if (r.get("Verification Status") or "").strip().lower() != "verified"
    )
    verified = [
        r for r in rows
        if (r.get("Verification Status") or "").strip().lower() == "verified"
    ]

    out_fields = list(rows[0].keys()) + [
        "non_uk_flag",
        "signal_type",
        "opener_line",
        "first_touch_subject",
        "first_touch_body",
        "second_touch_subject",
        "second_touch_body",
    ]

    output_rows: list[dict] = []
    no_first_name = 0
    no_company = 0
    non_uk_count = 0

    for idx, row in enumerate(verified):
        first_name = clean_first_name(row.get("First Name", ""))
        company_name = (row.get("companyName") or "").strip()
        founded_year = row.get("Founded Year", "")
        address = (row.get("Company Address") or "").strip()

        if not first_name:
            no_first_name += 1
        if not company_name:
            no_company += 1

        non_uk = is_non_uk(address)
        if non_uk:
            non_uk_count += 1

        signal = pick_signal(founded_year)
        template = templates.get(signal, templates["fallback"])
        opener = triggers[idx % len(triggers)]

        subj_template = template["first_touch"]["subject"]
        body_template = template["first_touch"]["body"]
        subj2_template = template["second_touch"]["subject"]
        body2_template = template["second_touch"]["body"]

        first_subject = render(subj_template, first_name, company_name, opener)
        first_body = render(body_template, first_name, company_name, opener)
        second_subject = render(subj2_template, first_name, company_name, opener)
        second_body = render(body2_template, first_name, company_name, opener)

        out_row = dict(row)
        out_row["non_uk_flag"] = "FLAG_NON_UK" if non_uk else ""
        out_row["signal_type"] = signal
        out_row["opener_line"] = opener
        out_row["first_touch_subject"] = first_subject
        out_row["first_touch_body"] = first_body
        out_row["second_touch_subject"] = second_subject
        out_row["second_touch_body"] = second_body
        output_rows.append(out_row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Input rows:       {len(rows)}")
    print(f"Dropped invalid:  {invalid_dropped}")
    print(f"Personalized:     {len(output_rows)}")
    print(f"  no first name:  {no_first_name}")
    print(f"  no company:     {no_company}")
    print(f"  FLAG_NON_UK:    {non_uk_count}  (operator should review/drop before Instantly upload)")
    by_signal: dict[str, int] = {}
    for r in output_rows:
        by_signal[r["signal_type"]] = by_signal.get(r["signal_type"], 0) + 1
    for sig, count in sorted(by_signal.items()):
        print(f"  signal={sig}: {count}")
    print(f"Output:           {out_path}")


if __name__ == "__main__":
    main()
