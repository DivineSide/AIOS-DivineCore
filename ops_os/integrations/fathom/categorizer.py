from openai import OpenAI

from settings import settings
from team import is_team_email

CATEGORIES = ("client", "strategy", "cofounder", "sales", "other")

CLIENT_DOMAINS: set[str] = set()
SALES_PROSPECT_EMAILS: set[str] = set()


def _domain(email: str) -> str:
    return email.split("@", 1)[-1].lower().strip() if "@" in email else ""


def _heuristic(payload: dict) -> str | None:
    invitees = payload.get("calendar_invitees") or []
    emails = [i.get("email", "").lower() for i in invitees if i.get("email")]
    if not emails:
        return None

    internal = [e for e in emails if is_team_email(e)]
    external = [e for e in emails if not is_team_email(e)]

    if not external:
        return "cofounder" if len(internal) == 2 else "strategy"

    if any(_domain(e) in CLIENT_DOMAINS for e in external):
        return "client"
    if any(e in SALES_PROSPECT_EMAILS for e in external):
        return "sales"
    return None


def _llm_fallback(payload: dict) -> str:
    client = OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )
    title = payload.get("meeting_title") or payload.get("title", "")
    raw_summary = payload.get("default_summary") or {}
    summary_text = raw_summary.get("markdown_formatted", "") if isinstance(raw_summary, dict) else str(raw_summary)
    summary = (summary_text or "")[:500]
    attendees = ", ".join(i.get("email", "") for i in payload.get("calendar_invitees") or [])
    prompt = (
        "Classify this meeting into exactly one category from: "
        f"{', '.join(CATEGORIES)}.\n\n"
        f"Title: {title}\n"
        f"Attendees: {attendees}\n"
        f"Summary excerpt: {summary}\n\n"
        "Respond with only the category word."
    )
    response = client.chat.completions.create(
        model=settings.CATEGORIZER_MODEL,
        max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (response.choices[0].message.content or "").strip().lower()
    return raw if raw in CATEGORIES else "other"


def classify(payload: dict) -> str:
    return _heuristic(payload) or _llm_fallback(payload)
