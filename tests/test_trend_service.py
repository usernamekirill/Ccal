from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from calorie_bot.app.services.trend_service import TrendService
from calorie_bot.app.trends.formatting import format_trend_report

TZ = ZoneInfo("Europe/Moscow")


class FakeStatsRepository:
    """Filters a static meal list by ``[start_at, end_at)`` like the real repo."""

    def __init__(self, meals: list) -> None:
        self._meals = meals

    async def list_confirmed_meals_between(
        self,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list:
        """Return meals whose timestamps fall in the half-open interval."""
        out = []
        for m in self._meals:
            if getattr(m, "user_id", 1) != user_id:
                continue
            et = m.eaten_at
            if et.tzinfo is None:
                et = et.replace(tzinfo=start_at.tzinfo)
            if start_at <= et < end_at:
                out.append(m)
        return out


class FakeProfileRepository:
    """Fixed profile for adherence tests."""

    def __init__(
        self,
        *,
        target: int = 2000,
        goal: str = "maintain_weight",
        timezone: str = "Europe/Moscow",
    ) -> None:
        self._target = target
        self._goal = goal
        self._timezone = timezone

    async def get_by_user_id(self, user_id: int):
        """Return a nutrition profile stub."""
        return SimpleNamespace(
            daily_calorie_target=self._target,
            goal=self._goal,
            timezone=self._timezone,
        )


def _meal(
    user_id: int,
    eaten_at: datetime,
    total_calories: int,
    source: str,
    item_name: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        eaten_at=eaten_at,
        total_calories=total_calories,
        source=source,
        items=[SimpleNamespace(name=item_name, calories=total_calories)],
    )


@pytest.mark.asyncio
async def test_trend_report_includes_chart_sources_and_change() -> None:
    """Trend report should aggregate days, sources, and compare to previous window."""
    current = [
        _meal(1, datetime(2026, 4, 24, 10, 0, tzinfo=TZ), 1500, "photo", "гречка"),
        _meal(1, datetime(2026, 4, 30, 12, 0, tzinfo=TZ), 1800, "audio", "салат"),
    ]
    previous = [
        _meal(1, datetime(2026, 4, 20, 12, 0, tzinfo=TZ), 2100, "text", "рис"),
    ]
    service = TrendService(
        stats_repository=FakeStatsRepository(current + previous),
        profile_repository=FakeProfileRepository(),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 18, 0, tzinfo=tz),
    )

    report = await service.build_report(1, 7)

    assert report.window_days == 7
    assert report.days_with_logs == 2
    assert report.days_without_logs == 5
    assert len(report.daily_points) == 7
    assert report.previous_window_avg is not None
    assert report.avg_change_vs_prev_percent is not None
    assert len(report.source_slices) >= 1
    assert report.top_products
    body = format_trend_report(report)
    assert "Калории по дням:" in body
    assert "█" in body
    assert "К прошлому отрезку:" in body


@pytest.mark.asyncio
async def test_trend_invalid_window_raises() -> None:
    """Only 7, 14, 30 day windows are valid."""
    service = TrendService(
        stats_repository=FakeStatsRepository([]),
        profile_repository=FakeProfileRepository(),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 18, 0, tzinfo=tz),
    )

    with pytest.raises(ValueError, match="trend_window"):
        await service.build_report(1, 5)
