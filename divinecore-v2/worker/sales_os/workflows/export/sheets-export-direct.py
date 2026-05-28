"""
Direct REST export to Google Sheets — bypasses httplib2 (workaround for
Windows IPv6 timeout issues affecting googleapiclient).

Reads token.json, calls Sheets REST API via `requests`. Same behavior as
sheets-export-us.py: writes a dated "Scrape YYYY-MM-DD" tab and appends
new unique leads to "All Leads" (dedup by email).

Usage:
  python workflows/export/sheets-export-direct.py <json_file> <spreadsheet_id> [--date YYYY-MM-DD]
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

ROOT = Path(__file__).resolve().parents[2]
TOKEN_PATH = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE = "https://sheets.googleapis.com/v4/spreadsheets"

HEADERS = [
    "First Name", "Last Name", "Email", "Personal Email", "Mobile",
    "Job Title", "Seniority", "LinkedIn",
    "Company", "Website", "Industry", "Employees",
    "City", "State", "Country",
    "Company Phone", "Company Address",
    "Founded Year", "Stage",
]


def get_token() -> str:
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds.token


def lead_to_row(lead: dict) -> list:
    return [
        lead.get("first_name", ""),
        lead.get("last_name", ""),
        lead.get("email", ""),
        lead.get("personal_email", "") or "",
        lead.get("mobile_number", "") or "",
        lead.get("job_title", ""),
        lead.get("seniority_level", ""),
        lead.get("linkedin", ""),
        lead.get("company_name", ""),
        lead.get("company_website", ""),
        lead.get("industry", ""),
        str(lead.get("company_size", "") or ""),
        lead.get("city", ""),
        lead.get("state", ""),
        lead.get("country", ""),
        lead.get("company_phone", "") or "",
        lead.get("company_full_address", "") or "",
        lead.get("company_founded_year", "") or "",
        "New",
    ]


def api(method: str, path: str, token: str, **kw) -> dict:
    r = requests.request(
        method,
        f"{BASE}/{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        **kw,
    )
    if r.status_code >= 400:
        print(f"ERROR {r.status_code}: {r.text[:600]}")
    r.raise_for_status()
    return r.json() if r.text else {}


def get_existing_emails(sid: str, token: str) -> set:
    try:
        data = api("GET", f"{sid}/values/All Leads!C2:C", token)
        return {row[0].lower().strip() for row in data.get("values", []) if row}
    except Exception:
        return set()


def get_tabs(sid: str, token: str) -> list:
    meta = api("GET", f"{sid}?fields=sheets(properties(title,sheetId))", token)
    return [s["properties"]["title"] for s in meta["sheets"]]


def add_tab(sid: str, title: str, token: str) -> None:
    body = {
        "requests": [{
            "addSheet": {
                "properties": {"title": title, "gridProperties": {"frozenRowCount": 1}}
            }
        }]
    }
    api("POST", f"{sid}:batchUpdate", token, json=body)


def write_values(sid: str, range_: str, values: list, token: str) -> None:
    api(
        "PUT",
        f"{sid}/values/{range_}?valueInputOption=RAW",
        token,
        json={"values": values},
    )


def append_values(sid: str, range_: str, values: list, token: str) -> None:
    api(
        "POST",
        f"{sid}/values/{range_}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        token,
        json={"values": values},
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("spreadsheet_id")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    leads = json.load(open(args.json_file, encoding="utf-8"))
    rows = [lead_to_row(l) for l in leads if l.get("email")]
    print(f"Loaded {len(rows)} leads with email from {args.json_file}")

    token = get_token()
    sid = args.spreadsheet_id

    tabs = get_tabs(sid, token)
    tab_name = f"Scrape {args.date}"
    if tab_name not in tabs:
        add_tab(sid, tab_name, token)
        print(f"Created tab: {tab_name}")
    if "All Leads" not in tabs:
        add_tab(sid, "All Leads", token)
        write_values(sid, "All Leads!A1", [HEADERS], token)
        print("Created tab: All Leads (with header)")

    write_values(sid, f"'{tab_name}'!A1", [HEADERS] + rows, token)
    print(f"Wrote {len(rows)} rows to '{tab_name}'")

    existing = get_existing_emails(sid, token)
    unique = [r for r in rows if r[2].lower().strip() not in existing]
    dupes = len(rows) - len(unique)

    if unique:
        append_values(sid, "All Leads!A1", unique, token)
    print(f"All Leads: +{len(unique)} new, {dupes} duplicates skipped")
    print(f"Total in 'All Leads': {len(existing) + len(unique)}")


if __name__ == "__main__":
    main()
