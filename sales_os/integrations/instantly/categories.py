"""Reply-category constants.

Instantly's AI labels each reply with a category string. We trust those labels
and never run our own classifier. The exact label vocabulary varies by Instantly
plan and account configuration — adjust the sets below as we observe real
payloads. Comparison is case-insensitive.
"""

# Replies that warrant an immediate Discord ping.
POSITIVE_CATEGORIES = {
    "interested",
    "meeting booked",
    "meeting_booked",
    "info request",
    "info_request",
}

# Replies that should NOT be stored as individual rows in outreach_replies.
# They still feed the daily aggregate counts via the analytics snapshot.
IGNORED_CATEGORIES = {
    "out of office",
    "out_of_office",
    "ooo",
    "auto reply",
    "auto-reply",
    "auto_reply",
    "automatic reply",
}


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def is_positive(category: str | None) -> bool:
    return _normalize(category) in POSITIVE_CATEGORIES


def is_ignored(category: str | None) -> bool:
    return _normalize(category) in IGNORED_CATEGORIES
