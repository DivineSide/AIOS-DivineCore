"""
One-shot script to fetch a Google OAuth refresh token. Run once, paste result into .env.

Usage (from divinecore-v2/):
    docker compose run --rm worker python -m integrations.upwork.oauth_bootstrap

Requires GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET in .env first.

Flow:
  1. Script prints an authorization URL — open it in your browser.
  2. Grant access. Google redirects to http://localhost:8080/?code=... — the page
     will fail to load (nothing serving on 8080) but the URL contains the code.
  3. Copy the full redirected URL (or just the code= value) and paste it back here.
  4. Script prints the refresh token. Paste it into .env as GOOGLE_OAUTH_REFRESH_TOKEN.
"""

from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow

from settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
REDIRECT_URI = "http://localhost:8080/"


def _extract_code(user_input: str) -> str:
    user_input = user_input.strip()
    if user_input.startswith("http"):
        params = parse_qs(urlparse(user_input).query)
        code = params.get("code", [""])[0]
        if not code:
            raise SystemExit("No `code` query param found in pasted URL.")
        return code
    return user_input


def main() -> None:
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise SystemExit("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env first.")

    flow = Flow.from_client_config(
        {
            "installed": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print("\n1. Open this URL in your browser:\n")
    print(auth_url)
    print(
        "\n2. Grant access. The browser will redirect to http://localhost:8080/?code=... "
        "and fail to load — that's expected.\n"
        "3. Copy the FULL redirected URL from the address bar (or just the code) and paste below.\n"
    )
    pasted = input("Paste here: ")
    code = _extract_code(pasted)

    flow.fetch_token(code=code)
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        raise SystemExit(
            "No refresh_token returned. Revoke previous access at "
            "https://myaccount.google.com/permissions and re-run."
        )

    print("\n--- SUCCESS ---")
    print("Paste this into .env:")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
