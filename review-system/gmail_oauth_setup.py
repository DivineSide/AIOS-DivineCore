"""
One-time script to get Gmail refresh token.
Run once, copy the refresh token into .env, never run again.

Steps:
1. Go to Google Cloud Console -> APIs & Services -> Gmail API -> Enable it
2. Run: python gmail_oauth_setup.py
3. Browser opens, sign in, grant permission
4. Copy the printed refresh token into .env as GMAIL_REFRESH_TOKEN
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import json

CLIENT_CONFIG = {
    "installed": {
        "client_id": "759847781829-bic4vjj7cerq42omcgvbef1oqlthdd8c.apps.googleusercontent.com",
        "client_secret": "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",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/"]
    }
}

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
creds = flow.run_local_server(port=8080)

print("\n=== COPY THIS INTO .env ===")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
print("===========================\n")
