"""Phone parsing + time-zone -> calling-block mapping for the dialer.

Pang is in Malaysia (UTC+8). US West is the sane "morning" block to dial first;
US Central + East come later as the "night" block. Edit BLOCK_MAP to retune.
"""

from __future__ import annotations

import phonenumbers
from phonenumbers import timezone as pn_tz

# IANA time zone -> calling block. The single place to change the schedule.
BLOCK_MAP: dict[str, str] = {
    # morning block = US West (best to call first from Malaysia)
    "America/Los_Angeles": "morning",
    "America/Denver": "morning",
    "America/Phoenix": "morning",
    # night block = US Central + East
    "America/Chicago": "night",
    "America/New_York": "night",
}


def parse_phone(raw: str | None) -> dict | None:
    """Return {phone, area_code, time_zone, calling_block} for a US number, or
    None if it won't parse / isn't a valid US number / has no usable time zone.
    """
    if not raw or not str(raw).strip():
        return None
    try:
        num = phonenumbers.parse(str(raw), "US")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None

    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    nsn = phonenumbers.national_significant_number(num)
    area_code = nsn[:3] if len(nsn) >= 10 else ""

    zones = [z for z in pn_tz.time_zones_for_number(num) if z and z != "Etc/Unknown"]
    if not zones:
        return None
    # Prefer a zone we have a block for; otherwise keep the first real zone.
    tz = next((z for z in zones if z in BLOCK_MAP), zones[0])

    return {
        "phone": e164,
        "area_code": area_code,
        "time_zone": tz,
        "calling_block": BLOCK_MAP.get(tz, ""),
    }
