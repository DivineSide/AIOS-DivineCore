"""Recreate the Ästhetik-Klinik Lead Sheet under patrick.munder@moic-ai.de."""

import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_authorized_user_file("token.json", SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())

sheets = build("sheets", "v4", credentials=creds)

# Create new spreadsheet
body = {
    "properties": {"title": "MOIC AI \u2014 Leads \u2014 \u00c4sthetik-Klinik DACH"},
    "sheets": [
        {"properties": {"title": "Alle Leads", "index": 0, "gridProperties": {"frozenRowCount": 1}}},
        {"properties": {"title": "Scrape 2026-04-11", "index": 1, "gridProperties": {"frozenRowCount": 1}}},
    ],
}
result = sheets.spreadsheets().create(body=body).execute()
new_sid = result["spreadsheetId"]
print(f"NEW SHEET ID: {new_sid}")
print(f"URL: {result['spreadsheetUrl']}")

# Load leads
with open("data/aesthetik-klinik-test-50.json", "r", encoding="utf-8") as f:
    leads = json.load(f)

# Headers (inkl. Copy-Spalten)
headers = [
    "Vorname", "Nachname", "E-Mail", "Pers\u00f6nliche E-Mail", "Handy",
    "Job Titel", "Seniority", "LinkedIn",
    "Firma", "Website", "Branche", "Mitarbeiter",
    "Stadt", "Bundesland", "Land",
    "Firmentelefon", "Firmenadresse",
    "Gr\u00fcndungsjahr", "Stage",
    "Research Notes", "Signal 1", "Signal 2",
    "Subject Line", "First Touch", "Second Touch Subject", "Second Touch",
]

rows = [headers]
for l in leads:
    rows.append([
        l.get("first_name", ""),
        l.get("last_name", ""),
        l.get("email", ""),
        l.get("personal_email", "") or "",
        l.get("mobile_number", "") or "",
        l.get("job_title", ""),
        l.get("seniority_level", ""),
        l.get("linkedin", ""),
        l.get("company_name", ""),
        l.get("company_website", ""),
        l.get("industry", ""),
        str(l.get("company_size", "") or ""),
        l.get("city", ""),
        l.get("state", ""),
        l.get("country", ""),
        l.get("company_phone", "") or "",
        l.get("company_full_address", "") or "",
        l.get("company_founded_year", "") or "",
        "New",
        "", "", "", "", "", "", "",
    ])

# Write to both tabs
for tab in ["Alle Leads", "Scrape 2026-04-11"]:
    sheets.spreadsheets().values().update(
        spreadsheetId=new_sid,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

# Format headers
for s in result["sheets"]:
    sheet_id = s["properties"]["sheetId"]
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=new_sid,
        body={"requests": [
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": len(headers),
                    }
                }
            },
        ]},
    ).execute()

print(f"Done! {len(leads)} leads written to both tabs.")
print(f"\nUpdate CLAUDE.md with new Sheet ID: {new_sid}")
