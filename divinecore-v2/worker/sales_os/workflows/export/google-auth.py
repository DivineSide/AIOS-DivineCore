"""
One-time Google OAuth bootstrap.

Reads credentials.json (OAuth client secret) and runs the browser auth flow
to generate token.json, which create-sheet-us.py and sheets-export-us.py load.

Run once:
  python workflows/export/google-auth.py

Opens a browser for you to authorize. Writes token.json next to credentials.json.
Re-run only if token.json is deleted or scopes change.
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.json"

# Superset of scopes needed by create-sheet (spreadsheets + drive) and export (spreadsheets)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main():
    if not CREDENTIALS_PATH.exists():
        print(f"ERROR: credentials.json not found at {CREDENTIALS_PATH}")
        return

    if TOKEN_PATH.exists():
        print(f"token.json already exists at {TOKEN_PATH}")
        print("Delete it first if you want to re-authorize.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"Authorized. token.json written to {TOKEN_PATH}")


if __name__ == "__main__":
    main()
