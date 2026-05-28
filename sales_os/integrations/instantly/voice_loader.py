"""Loads Pang's voice profile from shared/context/identity/pang.md.

Called by the drafter on every reply. Low volume so no caching; if voice
changes, the next draft picks it up automatically (no worker restart needed
when running with hot-reload volume mounts).

If shared/ isn't mounted/copied for some reason, returns empty string so the
drafter still runs (just less voice-aligned) rather than crashing the webhook.
"""

from pathlib import Path

# This file: /app/sales_os/integrations/instantly/voice_loader.py
# Target:    /app/shared/context/identity/pang.md
_PANG_MD = Path(__file__).resolve().parents[3] / "shared" / "context" / "identity" / "pang.md"


def load_pang_voice() -> str:
    try:
        return _PANG_MD.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
