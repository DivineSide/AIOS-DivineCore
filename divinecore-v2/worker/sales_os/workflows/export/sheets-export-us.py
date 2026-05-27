"""
Google Sheets Lead Export (US pipeline)
Exports scraped leads to Google Sheets with deduplication.

Structure per sheet:
  - "All Leads" tab: Master list, all leads deduplicated by email
  - "Scrape YYYY-MM-DD" tab: One tab per scrape run with date

Usage:
    python execution/export/sheets-export-us.py <json_file> <spreadsheet_id> [--date YYYY-MM-DD]
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
    "First Name", "Last Name", "Email", "Personal Email", "Mobile",
    "Job Title", "Seniority", "LinkedIn",
    "Company", "Website", "Industry", "Employees",
    "City", "State", "Country",
    "Company Phone", "Company Address",
    "Founded Year", "Stage",
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
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range="All Leads!C2:C"
        ).execute()
        values = result.get("values", [])
        return {row[0].lower().strip() for row in values if row}
    except Exception:
        return set()


def ensure_master_tab(service, spreadsheet_id, existing_tabs, meta):
    """Create 'All Leads' and 'Disqualified' tabs if they don't exist."""
    needed = []
    if "All Leads" not in existing_tabs:
        needed.append("All Leads")
    if "Disqualified" not in existing_tabs:
        needed.append("Disqualified")

    if not needed:
        return

    requests = [
        {"addSheet": {"properties": {"title": t, "gridProperties": {"frozenRowCount": 1}}}}
        for t in needed
    ]
    result = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()

    new_ids = {
        r["addSheet"]["properties"]["title"]: r["addSheet"]["properties"]["sheetId"]
        for r in result["replies"]
    }

    # Write headers
    data = []
    if "All Leads" in needed:
        data.append({"range": "All Leads!A1", "values": [HEADERS + ["Research Notes", "Style", "Opener Basis", "Subject (First Touch)", "First Touch Body", "Subject (Second Touch)", "Second Touch Body"]]})
    if "Disqualified" in needed:
        disq_headers = HEADERS + ["Reason", "Disqualified On"]
        data.append({"range": "Disqualified!A1", "values": [disq_headers]})

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    # Bold + grey header
    fmt = []
    for sheet_id in new_ids.values():
        fmt.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": fmt}).execute()
    print(f"Created missing tabs: {needed}")


def export_leads(json_file, spreadsheet_id, scrape_date=None):
    if scrape_date is None:
        scrape_date = date.today().isoformat()

    service = get_sheets_service()

    with open(json_file, "r", encoding="utf-8") as f:
        leads = json.load(f)

    new_rows = [lead_to_row(l) for l in leads if l.get("email")]
    print(f"Loaded {len(new_rows)} leads from {json_file}")

    tab_name = f"Scrape {scrape_date}"

    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_tabs = [s["properties"]["title"] for s in meta["sheets"]]

    ensure_master_tab(service, spreadsheet_id, existing_tabs, meta)
    # Refresh tab list after potential creation
    if "All Leads" not in existing_tabs or "Disqualified" not in existing_tabs:
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

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [HEADERS] + new_rows},
    ).execute()
    format_header(service, spreadsheet_id, scrape_sheet_id)
    print(f"Tab '{tab_name}': {len(new_rows)} leads exported")

    existing_emails = get_existing_emails(service, spreadsheet_id)
    unique_rows = [r for r in new_rows if r[2].lower().strip() not in existing_emails]
    dupes = len(new_rows) - len(unique_rows)

    if unique_rows:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="All Leads!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": unique_rows},
        ).execute()

    print(f"Tab 'All Leads': +{len(unique_rows)} new leads, {dupes} duplicates skipped")
    print(f"Total in 'All Leads': {len(existing_emails) + len(unique_rows)}")

    return {
        "scrape_tab": tab_name,
        "total_scraped": len(new_rows),
        "new_unique": len(unique_rows),
        "duplicates": dupes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sheets-export-us.py <json_file> <spreadsheet_id> [--date YYYY-MM-DD]")
        sys.exit(1)

    json_file = sys.argv[1]
    spreadsheet_id = sys.argv[2]
    scrape_date = None

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        scrape_date = sys.argv[idx + 1]

    result = export_leads(json_file, spreadsheet_id, scrape_date)
    print(json.dumps(result, indent=2))
