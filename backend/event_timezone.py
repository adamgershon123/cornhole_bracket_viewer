from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tzfpy import get_tz


def timezone_from_coordinates(latitude: object, longitude: object) -> str | None:
    try:
        name = get_tz(float(longitude), float(latitude))
        if not name:
            return None
        ZoneInfo(name)
        return name
    except (TypeError, ValueError, KeyError):
        return None


def advertised_start_utc(event_date: object, advertised_time: object, timezone_name: str) -> str | None:
    if not event_date or not advertised_time:
        return None
    raw = f"{event_date} {str(advertised_time).strip()}"
    parsed = None
    for pattern in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, pattern)
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    try:
        localized = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    except (KeyError, ValueError):
        return None
    return localized.astimezone(timezone.utc).isoformat()
