"""Calendar anchor for denormalized ``daily_stats`` (local midnight in user TZ)."""

from datetime import datetime, time
from zoneinfo import ZoneInfo


def stat_anchor_from_eaten_at(eaten_at: datetime, tz_name: str) -> datetime:
    """Return timezone-aware midnight for the local calendar day of ``eaten_at``."""
    tz = ZoneInfo(tz_name)
    local = eaten_at.astimezone(tz)
    return datetime.combine(local.date(), time.min, tzinfo=tz)
