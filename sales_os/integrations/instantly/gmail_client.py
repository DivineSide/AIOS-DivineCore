"""Gmail API client for the reply handler.

Auth via OAuth refresh token (GMAIL_OAUTH_*). Scopes: gmail.compose +
gmail.readonly. Refresh token obtained via gmail_oauth_bootstrap.py.

Two operations:
- find_thread_for_email(lead_email) -- locate the existing Gmail thread for
  a lead so the draft attaches to the right conversation.
- create_draft_reply(thread_id, to_email, subject, body) -- create a draft
  email (never auto-sends -- operator reviews + sends manually).
"""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _service() -> Any:
    creds = Credentials(
        token=None,
        refresh_token=settings.GMAIL_OAUTH_REFRESH_TOKEN,
        client_id=settings.GMAIL_OAUTH_CLIENT_ID,
        client_secret=settings.GMAIL_OAUTH_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def find_thread_for_email(lead_email: str, lookback_days: int = 30) -> tuple[str | None, str | None]:
    """Returns (thread_id, subject) of the most recent thread involving this
    lead, or (None, None) if no thread found in the lookback window."""
    if not lead_email:
        return None, None
    svc = _service()
    query = f"(from:{lead_email} OR to:{lead_email}) newer_than:{lookback_days}d"
    results = svc.users().messages().list(userId="me", q=query, maxResults=5).execute()
    msgs = results.get("messages", [])
    if not msgs:
        return None, None
    thread_id = msgs[0]["threadId"]
    subject = _get_thread_subject(svc, thread_id)
    return thread_id, subject


def _get_thread_subject(svc: Any, thread_id: str) -> str | None:
    thread = (
        svc.users()
        .threads()
        .get(userId="me", id=thread_id, format="metadata", metadataHeaders=["Subject"])
        .execute()
    )
    msgs = thread.get("messages", [])
    if not msgs:
        return None
    for h in msgs[0].get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == "subject":
            return h.get("value")
    return None


def create_draft_reply(
    *,
    thread_id: str | None,
    to_email: str,
    subject: str | None,
    body: str,
) -> dict:
    """Creates a Gmail draft. If thread_id provided, draft is attached so it
    threads correctly. Returns {draft_id, thread_id, gmail_url}."""
    svc = _service()
    mime = MIMEText(body, "plain", "utf-8")
    mime["To"] = to_email
    if subject:
        re_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        mime["Subject"] = re_subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

    payload: dict = {"message": {"raw": raw}}
    if thread_id:
        payload["message"]["threadId"] = thread_id

    draft = svc.users().drafts().create(userId="me", body=payload).execute()
    draft_id = draft.get("id")
    returned_thread_id = (draft.get("message") or {}).get("threadId") or thread_id

    gmail_url = (
        f"https://mail.google.com/mail/u/0/#all/{returned_thread_id}"
        if returned_thread_id
        else "https://mail.google.com/mail/u/0/#drafts"
    )
    return {
        "draft_id": draft_id,
        "thread_id": returned_thread_id,
        "gmail_url": gmail_url,
    }
