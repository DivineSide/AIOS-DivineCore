"""
Creates a new Google Sheet for an ICP with the standard 3-tab structure:
  - "Alle Leads" (master, deduplicated)
  - "Scrape YYYY-MM-DD" (first empty scrape tab, created when first scrape hits it)
  - "Disqualified" (rejected leads)

Header is written to "Alle Leads" and "Disqualified". Prints spreadsheet ID.

Usage:
  python execution/export/create-sheet.py <icp-name>
"""

import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
TOKEN_PATH = ROOT / "token.json"

HEADERS_ALLE = [
    "Vorname", "Nachname", "E-Mail", "Persoenliche E-Mail", "Handy",
    "Job Titel", "Seniority", "LinkedIn",
    "Firma", "Website", "Branche", "Mitarbeiter",
    "Stadt", "Bundesland", "Land",
    "Firmentelefon", "Firmenadresse",
    "Gruendungsjahr", "Stage",
    "Research Notes", "Style", "Opener Basis",
    "Subject (First Touch)", "First Touch Body",
    "Subject (Second Touch)", "Second Touch Body",
]

HEADERS_DISQ = HEADERS_ALLE[:19] + ["Grund", "Disqualified Am"]


def svc():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds)


ICP_TITLES = {
    "badstudio": "Badstudios DACH — Lead Pipeline",
    "fenster-tueren": "Fenster-/Haustürbauer DACH — Lead Pipeline",
    "zahnklinik": "Zahnkliniken (Privat) DACH — Lead Pipeline",
    "autohaus": "Autohaus DACH — Lead Pipeline",
    "poolbauer": "Poolbauer DACH — Lead Pipeline",
}


def main():
    icp = sys.argv[1]
    title = ICP_TITLES.get(icp, f"{icp} DACH — Lead Pipeline")

    s = svc()
    # Create spreadsheet with 3 tabs
    spec = {
        "properties": {"title": title},
        "sheets": [
            {"properties": {"title": "Alle Leads", "gridProperties": {"frozenRowCount": 1}}},
            {"properties": {"title": "Disqualified", "gridProperties": {"frozenRowCount": 1}}},
        ],
    }
    result = s.spreadsheets().create(body=spec, fields="spreadsheetId,sheets(properties(sheetId,title))").execute()
    sid = result["spreadsheetId"]
    print(f"Created: {title}")
    print(f"ID:      {sid}")
    print(f"URL:     https://docs.google.com/spreadsheets/d/{sid}")

    # Write headers
    s.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "Alle Leads!A1", "values": [HEADERS_ALLE]},
                {"range": "Disqualified!A1", "values": [HEADERS_DISQ]},
            ],
        },
    ).execute()

    # Bold + grey header row on both tabs
    tab_ids = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in result["sheets"]}
    fmt_requests = []
    for tab, sheet_id in tab_ids.items():
        fmt_requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
    s.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": fmt_requests}).execute()

    print("\nHeaders + formatting written.")
    print(f"\n>>> Paste this ID into CLAUDE.md for ICP '{icp}': {sid}")


if __name__ == "__main__":
    main()
