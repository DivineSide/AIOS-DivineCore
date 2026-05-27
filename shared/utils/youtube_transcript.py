"""
Extract a YouTube video's transcript via youtube-transcript-api.

CLI:
    python -m shared.utils.youtube_transcript <url-or-id> [--lang en] [--timestamps]
    python shared/utils/youtube_transcript.py <url-or-id> [--lang en] [--timestamps]

Importable:
    from shared.utils.youtube_transcript import fetch_transcript, extract_video_id
    text = fetch_transcript("https://youtu.be/dQw4w9WgXcQ")

Requires: pip install youtube-transcript-api
"""

from __future__ import annotations

import argparse
import re
import sys
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url_or_id: str) -> str:
    """Accept a raw video ID or any common YouTube URL form and return the 11-char ID."""
    s = url_or_id.strip()
    if _VIDEO_ID_RE.match(s):
        return s

    parsed = urlparse(s)
    host = (parsed.hostname or "").lower().lstrip("www.")

    if host in {"youtu.be"}:
        candidate = parsed.path.lstrip("/").split("/")[0]
        if _VIDEO_ID_RE.match(candidate):
            return candidate

    if host.endswith("youtube.com") or host == "youtube.com":
        # /watch?v=ID
        v = parse_qs(parsed.query).get("v", [None])[0]
        if v and _VIDEO_ID_RE.match(v):
            return v
        # /shorts/ID, /embed/ID, /live/ID, /v/ID
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
            if _VIDEO_ID_RE.match(parts[1]):
                return parts[1]

    raise ValueError(f"Could not extract YouTube video ID from: {url_or_id!r}")


def fetch_transcript(
    url_or_id: str,
    languages: list[str] | None = None,
    with_timestamps: bool = False,
) -> str:
    """Fetch the transcript and return a single string.

    languages: priority-ordered list of language codes, e.g. ["en", "en-US"]. Defaults to ["en"].
    with_timestamps: prefix each line with [MM:SS] when True.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as e:
        raise ImportError(
            "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"
        ) from e

    video_id = extract_video_id(url_or_id)
    langs = languages or ["en"]
    fetched = YouTubeTranscriptApi().fetch(video_id, languages=langs)

    if not with_timestamps:
        return " ".join(s.text.replace("\n", " ").strip() for s in fetched if s.text)

    lines = []
    for s in fetched:
        text = (s.text or "").replace("\n", " ").strip()
        if not text:
            continue
        start = int(s.start)
        mm, ss = divmod(start, 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {text}")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract a YouTube video transcript.")
    p.add_argument("url_or_id", help="YouTube URL or 11-char video ID")
    p.add_argument(
        "--lang",
        default="en",
        help="Comma-separated language priority list (default: en). e.g. en,en-US,en-GB",
    )
    p.add_argument("--timestamps", action="store_true", help="Prefix each line with [MM:SS]")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    languages = [l.strip() for l in args.lang.split(",") if l.strip()]
    try:
        out = fetch_transcript(args.url_or_id, languages=languages, with_timestamps=args.timestamps)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
