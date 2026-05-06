"""Calendar anchor for denormalized ``daily_stats`` (local midnight in user TZ)."""

from datetime import datetime, time
from zoneinfo import ZoneInfo


def stat_anchor_from_eaten_at(eaten_at: datetime, tz_name: str) -> datetime:
    """Return timezone-aware midnight for the local calendar day of ``eaten_at``.

    SQLite (and some drivers) return *naive* datetimes for ``DateTime(timezone=True)``.
    In that case we interpret the stored wall clock as already expressed in ``tz_name``
    (the user's calendar day for stats), rather than applying the server's local timezone.
    """
    tz = ZoneInfo(tz_name)
    if eaten_at.tzinfo is None:
        local = eaten_at.replace(tzinfo=tz)
    else:
        local = eaten_at.astimezone(tz)
    return datetime.combine(local.date(), time.min, tzinfo=tz)
