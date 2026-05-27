"""
Fetch the dataset from the last completed Apify run and save it locally.
Tries APIFY_API_KEY_1, _2, _3 in order until one returns real data.

Usage:
  python workflows/scrape/fetch-last-run.py <icp> [--actor <actor_id>]

Output: data/<icp>-<date>.json

Then filter with:
  python workflows/scrape/filter-leads-us.py <icp> --client <client> data/<icp>-<date>.json --out data/<icp>-<date>-filtered.json
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

_SCRIPT = Path(__file__).resolve()
ROOT = _SCRIPT.parents[2]
load_dotenv(_SCRIPT.parents[5] / ".env")

DEFAULT_ACTOR = "code_crafter~leads-finder"
FREE_PLAN_MSG = "users on the free apify plan can run the actor through the ui"


def load_tokens() -> list[str]:
    tokens = []
    for i in range(1, 10):
        val = os.environ.get(f"APIFY_API_KEY_{i}", "").strip()
        if val:
            tokens.append(val)
    return tokens


def get_last_succeeded_run(actor: str, token: str) -> dict | None:
    r = requests.get(
        f"https://api.apify.com/v2/acts/{actor}/runs",
        params={"token": token, "limit": 5, "desc": True},
        timeout=30,
    )
    if r.status_code == 403:
        return None
    r.raise_for_status()
    for run in r.json().get("data", {}).get("items", []):
        if run.get("status") == "SUCCEEDED":
            return run
    return None


def fetch_dataset(dataset_id: str, token: str) -> list[dict] | None:
    r = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": token, "format": "json", "clean": "true"},
        timeout=120,
    )
    if r.status_code >= 400:
        return None
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("icp")
    ap.add_argument("--actor", default=DEFAULT_ACTOR)
    ap.add_argument("--run-id", default=None, help="Specific run ID from Apify console URL")
    ap.add_argument("--dataset-id", default=None, help="Specific dataset ID (shown in run details)")
    args = ap.parse_args()

    tokens = load_tokens()
    if not tokens:
        print("ERROR: no APIFY_API_KEY_N found in .env")
        sys.exit(1)

    # Direct fetch by run/dataset ID — useful when the run was done from a browser account
    if args.dataset_id or args.run_id:
        token = tokens[0]
        if args.dataset_id:
            dataset_id = args.dataset_id
        else:
            r = requests.get(
                f"https://api.apify.com/v2/actor-runs/{args.run_id}",
                params={"token": token},
                timeout=30,
            )
            r.raise_for_status()
            dataset_id = r.json()["data"]["defaultDatasetId"]

        items = fetch_dataset(dataset_id, token)
        if not items:
            print("ERROR: dataset empty or inaccessible.")
            sys.exit(1)

        out_dir = ROOT / "data"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{args.icp}-{date.today().isoformat()}.json"
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{len(items)} leads saved to {out_path}")
        print(f"\nNext step:")
        print(f"  python workflows/scrape/filter-leads-us.py {args.icp} --client divinecore {out_path.name} --out data/{args.icp}-filtered.json")
        return

    print(f"Actor: {args.actor}")

    for idx, token in enumerate(tokens, start=1):
        run = get_last_succeeded_run(args.actor, token)
        if not run:
            print(f"  Key #{idx}: no completed run found.")
            continue

        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]
        print(f"  Key #{idx}: run {run_id} finished at {run.get('finishedAt', '?')}")

        items = fetch_dataset(dataset_id, token)

        if items is None:
            print(f"  Key #{idx}: failed to fetch dataset.")
            continue
        if items and isinstance(items[0], dict) and FREE_PLAN_MSG in items[0].get("error", "").lower():
            print(f"  Key #{idx}: dataset blocked (free plan).")
            continue
        if not items:
            print(f"  Key #{idx}: dataset empty.")
            continue

        out_dir = ROOT / "data"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{args.icp}-{date.today().isoformat()}.json"
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n{len(items)} leads saved to {out_path}")
        print(f"\nNext step:")
        print(f"  python workflows/scrape/filter-leads-us.py {args.icp} --client divinecore {out_path.name} --out data/{args.icp}-filtered.json")
        return

    print("ERROR: no usable dataset found across all API keys.")
    sys.exit(1)


if __name__ == "__main__":
    main()
