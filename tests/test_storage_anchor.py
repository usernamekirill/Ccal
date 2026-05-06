"""Tests for local-day anchoring used by ``daily_stats`` denormalization."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from calorie_bot.app.utils.stat_anchor import stat_anchor_from_eaten_at


def test_stat_anchor_aligns_to_local_midnight() -> None:
    """Anchor is start of calendar day in the given IANA zone."""
    tz = ZoneInfo("Europe/Moscow")
    eaten = datetime(2026, 4, 30, 23, 0, tzinfo=ZoneInfo("UTC")).astimezone(tz)
    anchor = stat_anchor_from_eaten_at(eaten, "Europe/Moscow")
    assert anchor.tzinfo == tz
    assert anchor.time() == time.min
    assert anchor.date() == eaten.date()


def test_stat_anchor_naive_wall_time_uses_user_zone_not_server_local() -> None:
    """SQLite returns naive datetimes; treat them as wall time in the user's IANA zone.

    :meth:`~datetime.datetime.astimezone` on naive values uses the *server* local
    timezone and can shift the calendar day (breaking ``daily_stats`` rollups).
    """
    tz = ZoneInfo("Europe/Moscow")
    naive_local = datetime(2026, 5, 2, 14, 0, 0)
    anchor = stat_anchor_from_eaten_at(naive_local, "Europe/Moscow")
    assert anchor == datetime(2026, 5, 2, 0, 0, 0, tzinfo=tz)
