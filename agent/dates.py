from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DHAKA = ZoneInfo("Asia/Dhaka")
NEW_YORK = ZoneInfo("America/New_York")

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def bn_to_ascii(s: str) -> str:
    """Convert Bangla digits (০-৯) to ASCII digits."""
    return s.translate(_BN_DIGITS)


def parse(text: str, fmt: str, tz) -> datetime | None:
    """Parse the first match of `fmt` in `text`; return None if it does not parse."""
    try:
        return datetime.strptime(text.strip(), fmt).replace(tzinfo=tz)
    except (ValueError, AttributeError):
        return None


def parse_gmt_offset(text: str) -> datetime | None:
    """UNGM style: '02-Nov-2026 13:00 (GMT 3.00)' or '(GMT -4.00)'."""
    m = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2})\s*\(GMT\s*(-?\d+(?:\.\d+)?)\)", text)
    if not m:
        m2 = re.search(r"\d{2}-[A-Za-z]{3}-\d{4}", text)
        return parse(m2.group(0), "%d-%b-%Y", timezone.utc) if m2 else None
    hours = float(m.group(2))
    tz = timezone(timedelta(minutes=round(hours * 60)))
    return parse(m.group(1), "%d-%b-%Y %H:%M", tz)


def now() -> datetime:
    return datetime.now(timezone.utc)


def is_since(published: datetime | None, since: datetime) -> bool:
    """True when published on or after `since` (compared by calendar date, so date-only values count)."""
    if published is None:
        return True  # unknown date: let dedup decide rather than silently dropping it
    return published.astimezone(DHAKA).date() >= since.astimezone(DHAKA).date()
