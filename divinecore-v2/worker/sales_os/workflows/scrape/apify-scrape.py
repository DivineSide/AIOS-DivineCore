"""
Apify Scrape — code_crafter/leads-finder (Apollo wrapper).

Usage:
  python execution/scrape/apify-scrape.py <icp-name> --client <client-name> [--count 50] [--wait]

Reads filters from clients/<client>/icps/<icp-name>/scrape.yaml.
Writes raw output to data/<icp-name>-YYYY-MM-DD.json.

API key rotation: tries APIFY_API_KEY_1, then _2, then _3.
Rotates on HTTP 402 (credits exhausted) or Apify usage-limit errors.
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

_SCRIPT = Path(__file__).resolve()
ROOT = _SCRIPT.parents[2]          # sales_os/ — base for Clients/ and data/
load_dotenv(_SCRIPT.parents[5] / ".env")  # DivineSide/.env

ACTOR = "code_crafter~leads-finder"

SIZE_BUCKETS = [
    ("1-10", 1, 10),
    ("11-20", 11, 20),
    ("21-50", 21, 50),
    ("51-100", 51, 100),
    ("101-200", 101, 200),
    ("201-500", 201, 500),
    ("501-1000", 501, 1000),
    ("1001-2000", 1001, 2000),
    ("2001-5000", 2001, 5000),
    ("5001-10000", 5001, 10000),
    ("10001-20000", 10001, 20000),
    ("20001-50000", 20001, 50000),
]

CREDIT_ERROR_TYPES = {
    "USAGE_LIMIT_EXCEEDED",
    "PLAN_USAGE_LIMIT_EXCEEDED",
    "ACTOR_USAGE_LIMIT_EXCEEDED",
}

PERMISSION_ERROR_TYPE = "full-permission-actor-not-approved"


def load_tokens() -> list[str]:
    tokens = []
    for i in range(1, 10):
        val = os.environ.get(f"APIFY_API_KEY_{i}", "").strip()
        if val:
            tokens.append(val)
    if not tokens:
        # fallback to old single-key name
        val = os.environ.get("APIFY_API_TOKEN", "").strip()
        if val:
            tokens.append(val)
    return tokens


def pick_sizes(min_emp: int, max_emp: int) -> list[str]:
    return [label for label, lo, hi in SIZE_BUCKETS if hi >= min_emp and lo <= max_emp]


def build_input(cfg: dict, count: int, file_name: str) -> dict:
    f = cfg["filters"]
    ec = f["employee_count"]

    chains = cfg.get("filters", {}).get("exclude_companies", {}).get("chains") or []
    top_chains = cfg.get("exclude_companies", {}).get("chains") or []
    all_chains = list(set(chains + top_chains))
    not_keywords = list(f["company_keywords"].get("exclude_any", [])) + all_chains

    return {
        "fetch_count": count,
        "file_name": file_name,
        "contact_job_title": f["titles"]["include"],
        "contact_not_job_title": f["titles"]["exclude"],
        "seniority_level": cfg.get("seniority_level", ["founder", "owner", "c_suite"]),
        "contact_location": f["locations"],
        "company_industry": f["industries"]["include"],
        "size": pick_sizes(ec["min"], ec["max"]),
        "company_keywords": f["company_keywords"]["include_any"],
        "company_not_keywords": not_keywords,
        "email_status": ["validated"],
    }


def _is_credit_error(status_code: int, body: dict) -> bool:
    if status_code == 402:
        return True
    error_type = body.get("error", {}).get("type", "")
    return error_type in CREDIT_ERROR_TYPES


def _check_permission_error(status_code: int, body: dict) -> str | None:
    """Returns approval URL if permissions not granted, else None."""
    if status_code == 403 and body.get("error", {}).get("type") == PERMISSION_ERROR_TYPE:
        return body.get("error", {}).get("data", {}).get("approvalUrl", "")
    return None


def start_run(payload: dict, token: str) -> tuple[str, str]:
    url = f"https://api.apify.com/v2/acts/{ACTOR}/runs?token={token}"
    r = requests.post(url, json=payload, timeout=60)
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    if _is_credit_error(r.status_code, body):
        raise CreditExhaustedError(f"HTTP {r.status_code}: {body.get('error', {}).get('message', 'credits exhausted')}")
    approval_url = _check_permission_error(r.status_code, body)
    if approval_url:
        raise CreditExhaustedError(f"permissions not approved — approve at: {approval_url}")
    if r.status_code >= 400:
        print(f"ERROR {r.status_code}: {r.text[:500]}")
    r.raise_for_status()
    run = body["data"]
    return run["id"], run["defaultDatasetId"]


FREE_PLAN_MSG = "users on the free apify plan can run the actor through the ui"


def _is_free_plan_block(items: list[dict]) -> bool:
    if not items:
        return False
    first = items[0]
    return isinstance(first, dict) and FREE_PLAN_MSG in first.get("error", "").lower()


def run_scrape(payload: dict, tokens: list[str], do_wait: bool) -> tuple[list[dict] | None, str, str, str]:
    """Try each token. Returns (items_or_None, run_id, dataset_id, token_used).
    items is None when do_wait=False (caller polls manually)."""
    for idx, token in enumerate(tokens, start=1):
        try:
            run_id, dataset_id = start_run(payload, token)
            if idx > 1:
                print(f"  Using API key #{idx}")
            print(f"Run started: {run_id}")
            print(f"Dataset:     {dataset_id}")
            print(f"Console:     https://console.apify.com/actors/runs/{run_id}")

            if not do_wait:
                return None, run_id, dataset_id, token

            print("\nWaiting for run to finish...")
            status = wait_for_run(run_id, token)
            if status != "SUCCEEDED":
                print(f"  Run {status} on key #{idx}. Trying next...")
                raise CreditExhaustedError(f"Run status: {status}")

            items = fetch_dataset(dataset_id, token)
            if _is_free_plan_block(items):
                raise CreditExhaustedError(f"Key #{idx}: free plan blocks API — rotating")

            return items, run_id, dataset_id, token

        except CreditExhaustedError as e:
            print(f"  API key #{idx} failed: {e}. Trying next...")

    print("ERROR: all Apify API keys exhausted or blocked. Add more keys or upgrade a plan.")
    sys.exit(1)


def wait_for_run(run_id: str, token: str, poll: int = 10) -> str:
    url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}"
    while True:
        r = requests.get(url, timeout=30).json()["data"]
        status = r["status"]
        print(f"  [{r.get('stats',{}).get('runTimeSecs', '?')}s] status={status}")
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            return status
        time.sleep(poll)


def fetch_dataset(dataset_id: str, token: str) -> list[dict]:
    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}&format=json&clean=true"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.json()


class CreditExhaustedError(Exception):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("icp")
    ap.add_argument("--client", required=True, help="Client folder name, e.g. divinecore")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--wait", action="store_true", help="Block until run finishes")
    ap.add_argument("--suffix", default="", help="Optional tag for output file")
    args = ap.parse_args()

    tokens = load_tokens()
    if not tokens:
        print("ERROR: no Apify API keys found. Set APIFY_API_KEY_1 (and optionally _2, _3) in .env")
        sys.exit(1)

    cfg_path = ROOT / "Clients" / args.client / "icps" / args.icp / "scrape.yaml"
    if not cfg_path.exists():
        print(f"ERROR: scrape config not found at {cfg_path}")
        sys.exit(1)

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    today = date.today().isoformat()
    stem = f"{args.icp}-{args.suffix + '-' if args.suffix else ''}{today}"
    file_name = stem + "-apify"

    payload = build_input(cfg, args.count, file_name)
    print(f"Client:     {args.client}")
    print(f"ICP:        {args.icp}")
    print(f"Count:      {args.count}")
    print(f"Industries: {payload['company_industry']}")
    print(f"Sizes:      {payload['size']}")
    print(f"Keywords+:  {len(payload['company_keywords'])} items")
    print(f"Keywords-:  {len(payload['company_not_keywords'])} items")
    print(f"API keys:   {len(tokens)} loaded")
    print()

    items, run_id, dataset_id, active_token = run_scrape(payload, tokens, args.wait)

    if not args.wait:
        print("\nUse --wait to block until finished.")
        return

    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{stem}.json"
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(items)} leads written to {out_path}")


if __name__ == "__main__":
    main()
