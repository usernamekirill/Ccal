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
