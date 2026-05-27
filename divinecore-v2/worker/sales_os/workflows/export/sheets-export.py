"""
Google Sheets Lead Export
Exports scraped leads to Google Sheets with deduplication.

Structure per sheet:
  - "Alle Leads" tab: Master list, all leads deduplicated by email
  - "Scrape YYYY-MM-DD" tab: One tab per scrape run with date

Usage:
    python execution/export/sheets-export.py <json_file> <spreadsheet_id> [--date YYYY-MM-DD]
"""

import json
import sys
import os
from datetime import date
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "token.json")

HEADERS = [
    "Vorname", "Nachname", "E-Mail", "Persoenliche E-Mail", "Handy",
    "Job Titel", "Seniority", "LinkedIn",
    "Firma", "Website", "Branche", "Mitarbeiter",
    "Stadt", "Bundesland", "Land",
    "Firmentelefon", "Firmenadresse",
    "Gruendungsjahr", "Stage",
]


def get_sheets_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def lead_to_row(lead):
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


def format_header(service, spreadsheet_id, sheet_id):
    requests = [
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
                    "endIndex": len(HEADERS),
                }
            }
        },
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()


def get_existing_emails(service, spreadsheet_id):
    """Read all emails from the 'Alle Leads' master tab."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range="Alle Leads!C2:C"
        ).execute()
        values = result.get("values", [])
        return {row[0].lower().strip() for row in values if row}
    except Exception:
        return set()


def export_leads(json_file, spreadsheet_id, scrape_date=None):
    if scrape_date is None:
        scrape_date = date.today().isoformat()

    service = get_sheets_service()

    # Load new leads
    with open(json_file, "r", encoding="utf-8") as f:
        leads = json.load(f)

    new_rows = [lead_to_row(l) for l in leads if l.get("email")]
    print(f"Loaded {len(new_rows)} leads from {json_file}")

    # --- Step 1: Create dated scrape tab ---
    tab_name = f"Scrape {scrape_date}"

    # Get existing sheet names
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_tabs = [s["properties"]["title"] for s in meta["sheets"]]

    if tab_name not in existing_tabs:
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": tab_name,
                                "gridProperties": {"frozenRowCount": 1},
                            }
                        }
                    }
                ]
            },
        ).execute()
        scrape_sheet_id = result["replies"][0]["addSheet"]["properties"]["sheetId"]
    else:
        scrape_sheet_id = next(
            s["properties"]["sheetId"]
            for s in meta["sheets"]
            if s["properties"]["title"] == tab_name
        )

    # Write all leads (incl. header) to scrape tab
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [HEADERS] + new_rows},
    ).execute()
    format_header(service, spreadsheet_id, scrape_sheet_id)
    print(f"Tab '{tab_name}': {len(new_rows)} leads exported")

    # --- Step 2: Dedup and update master tab ---
    existing_emails = get_existing_emails(service, spreadsheet_id)
    unique_rows = [r for r in new_rows if r[2].lower().strip() not in existing_emails]
    dupes = len(new_rows) - len(unique_rows)

    if unique_rows:
        # Append only new unique leads to master tab
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Alle Leads!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": unique_rows},
        ).execute()

    print(f"Tab 'Alle Leads': +{len(unique_rows)} neue Leads, {dupes} Duplikate uebersprungen")
    print(f"Gesamt in 'Alle Leads': {len(existing_emails) + len(unique_rows)}")

    return {
        "scrape_tab": tab_name,
        "total_scraped": len(new_rows),
        "new_unique": len(unique_rows),
        "duplicates": dupes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sheets-export.py <json_file> <spreadsheet_id> [--date YYYY-MM-DD]")
        sys.exit(1)

    json_file = sys.argv[1]
    spreadsheet_id = sys.argv[2]
    scrape_date = None

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        scrape_date = sys.argv[idx + 1]

    result = export_leads(json_file, spreadsheet_id, scrape_date)
    print(json.dumps(result, indent=2))
