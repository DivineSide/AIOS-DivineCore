"""
Creates a new Google Sheet for a US ICP with the standard 3-tab structure:
  - "All Leads" (master, deduplicated)
  - "Disqualified" (rejected leads)

Header is written to both tabs. Prints spreadsheet ID.

Usage:
  python execution/export/create-sheet-us.py <icp-name>

ICP names: aesthetic-clinic-us, real-estate-broker-us, car-dealership-us
"""

import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
TOKEN_PATH = ROOT / "token.json"

HEADERS_ALL = [
    "First Name", "Last Name", "Email", "Personal Email", "Mobile",
    "Job Title", "Seniority", "LinkedIn",
    "Company", "Website", "Industry", "Employees",
    "City", "State", "Country",
    "Company Phone", "Company Address",
    "Founded Year", "Stage",
    "Research Notes", "Style", "Opener Basis",
    "Subject (First Touch)", "First Touch Body",
    "Subject (Second Touch)", "Second Touch Body",
]

HEADERS_DISQ = HEADERS_ALL[:19] + ["Reason", "Disqualified On"]

ICP_TITLES = {
    "aesthetic-clinic-us": "Aesthetic Clinics US — Lead Pipeline",
    "real-estate-broker-us": "Real Estate Brokers US — Lead Pipeline",
    "car-dealership-us": "Car Dealerships US — Lead Pipeline",
}


def svc():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def main():
    icp = sys.argv[1]
    title = ICP_TITLES.get(icp, f"{icp} US — Lead Pipeline")

    s = svc()
    spec = {
        "properties": {"title": title},
        "sheets": [
            {"properties": {"title": "All Leads", "gridProperties": {"frozenRowCount": 1}}},
            {"properties": {"title": "Disqualified", "gridProperties": {"frozenRowCount": 1}}},
        ],
    }
    result = s.spreadsheets().create(body=spec, fields="spreadsheetId,sheets(properties(sheetId,title))").execute()
    sid = result["spreadsheetId"]
    print(f"Created: {title}")
    print(f"ID:      {sid}")
    print(f"URL:     https://docs.google.com/spreadsheets/d/{sid}")

    s.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "All Leads!A1", "values": [HEADERS_ALL]},
                {"range": "Disqualified!A1", "values": [HEADERS_DISQ]},
            ],
        },
    ).execute()

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
