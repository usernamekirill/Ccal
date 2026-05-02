from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from calorie_bot.app.services.stats_service import StatsService
from calorie_bot.app.stats.formatting import format_progress_bar, format_today_stats

TZ = ZoneInfo("Europe/Moscow")


class FakeStatsRepository:
    """In-memory stats repository for unit tests."""

    def __init__(self, meals: list) -> None:
        self._meals = meals

    async def list_confirmed_meals_between(
        self,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list:
        """Return meals whose ``eaten_at`` falls in ``[start_at, end_at)``."""
        out: list = []
        for meal in self._meals:
            uid = getattr(meal, "user_id", 1)
            if uid != user_id:
                continue
            eaten = meal.eaten_at
            if eaten.tzinfo is None:
                eaten = eaten.replace(tzinfo=start_at.tzinfo)
            if start_at <= eaten < end_at:
                out.append(meal)
        return out


class FakeProfileRepository:
    """Minimal profile source for stats tests."""

    def __init__(
        self,
        calorie_target: int | None = 2000,
        timezone: str = "Europe/Moscow",
    ) -> None:
        self._calorie_target = calorie_target
        self._timezone = timezone

    async def get_by_user_id(self, user_id: int):
        """Return a namespace mimicking ``UserProfile`` fields used by stats."""
        return SimpleNamespace(
            daily_calorie_target=self._calorie_target,
            timezone=self._timezone,
        )


def _meal(
    user_id: int,
    eaten_at: datetime,
    total_calories: int,
    item_calories: int | None = None,
    *,
    total_calories_min: int | None = None,
    total_calories_max: int | None = None,
    has_estimated_items: bool = False,
) -> SimpleNamespace:
    """Build a lightweight meal row."""
    kcal = item_calories if item_calories is not None else total_calories
    return SimpleNamespace(
        user_id=user_id,
        eaten_at=eaten_at,
        total_calories=total_calories,
        total_calories_min=total_calories_min,
        total_calories_max=total_calories_max,
        has_estimated_items=has_estimated_items,
        items=[SimpleNamespace(name="тест", calories=kcal)],
    )


@pytest.mark.asyncio
async def test_today_view_shows_goal_progress_and_food() -> None:
    """Today view should sum meals, compare to target, and list foods."""
    meal = _meal(
        user_id=1,
        eaten_at=datetime(2026, 4, 30, 10, 15, tzinfo=TZ),
        total_calories=500,
    )
    service = StatsService(
        stats_repository=FakeStatsRepository([meal]),
        profile_repository=FakeProfileRepository(calorie_target=2000),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 18, 0, tzinfo=tz),
    )

    view = await service.today_view(1)

    assert view.total_calories == 500
    assert view.calorie_target == 2000
    assert view.remaining_kcal == 1500
    assert view.progress_percent == 25.0
    assert view.meals_count == 1
    assert any("10:15" in line for line in view.food_sections)

    body = format_today_stats(view)
    assert "500" in body
    assert "2000" in body
    assert "Прогресс:" in body


@pytest.mark.asyncio
async def test_today_view_calorie_band_and_estimated_ratio() -> None:
    """Meals with calorie min/max produce a day band; estimated_meals_ratio is filled."""
    m1 = _meal(
        1,
        datetime(2026, 4, 30, 10, 15, tzinfo=TZ),
        200,
        total_calories_min=180,
        total_calories_max=220,
        has_estimated_items=True,
    )
    m2 = _meal(
        1,
        datetime(2026, 4, 30, 14, 0, tzinfo=TZ),
        300,
        has_estimated_items=False,
    )
    service = StatsService(
        stats_repository=FakeStatsRepository([m1, m2]),
        profile_repository=FakeProfileRepository(calorie_target=2000),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 18, 0, tzinfo=tz),
    )
    view = await service.today_view(1)

    assert view.total_calories == 500
    assert view.total_calories_min == 480
    assert view.total_calories_max == 520
    assert view.estimated_meals_ratio == 0.5
    txt = format_today_stats(view)
    assert "480" in txt and "520" in txt


@pytest.mark.asyncio
async def test_week_view_counts_days_against_target() -> None:
    """Week view uses Mon–Sun in profile timezone and adherence counts."""
    meals = [
        _meal(1, datetime(2026, 4, 29, 12, 0, tzinfo=TZ), 1800),
        _meal(1, datetime(2026, 4, 30, 12, 0, tzinfo=TZ), 2200),
    ]
    service = StatsService(
        stats_repository=FakeStatsRepository(meals),
        profile_repository=FakeProfileRepository(calorie_target=2000),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 12, 0, tzinfo=tz),
    )

    view = await service.week_view(1)

    assert view.days_with_logs == 2
    assert view.days_above_target == 1
    assert view.days_below_or_equal_target == 1
    assert view.best_day_calories in (1800, 2200)
    assert view.avg_calories_per_day is not None
    assert pytest.approx(view.avg_calories_per_day, rel=1e-3) == (1800 + 2200) / 7.0


@pytest.mark.asyncio
async def test_month_view_regularity_and_trend() -> None:
    """Month view averages by elapsed days and computes a simple trend label."""
    meals: list[SimpleNamespace] = []
    for day, kcal in ((1, 1500), (5, 1600), (10, 1400), (20, 2100)):
        meals.append(
            _meal(
                1,
                datetime(2026, 4, day, 9, 0, tzinfo=TZ),
                kcal,
            )
        )
    service = StatsService(
        stats_repository=FakeStatsRepository(meals),
        profile_repository=FakeProfileRepository(calorie_target=2000),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 8, 0, tzinfo=tz),
    )

    view = await service.month_view(1)

    assert view.days_with_data == 4
    assert view.days_elapsed_in_month == 30
    assert view.regularity_percent is not None
    assert pytest.approx(view.regularity_percent, rel=1e-6) == 100.0 * 4 / 30
    assert view.trend_label != "мало данных"


@pytest.mark.asyncio
async def test_get_calorie_trend_includes_deviation_and_moving_average() -> None:
    """Trend uses one repository fetch and computes deviation vs goal."""
    from datetime import date

    meals = [
        _meal(1, datetime(2026, 4, 28, 12, 0, tzinfo=TZ), 1500),
        _meal(1, datetime(2026, 4, 29, 12, 0, tzinfo=TZ), 1800),
        _meal(1, datetime(2026, 4, 30, 12, 0, tzinfo=TZ), 2000),
    ]
    service = StatsService(
        stats_repository=FakeStatsRepository(meals),
        profile_repository=FakeProfileRepository(calorie_target=2000),
        default_timezone="Europe/Moscow",
        now_factory=lambda tz: datetime(2026, 4, 30, 12, 0, tzinfo=tz),
    )
    trend = await service.get_calorie_trend(1, window_days=3, moving_avg_window=2)
    assert len(trend) == 3
    assert trend[-1].day == date(2026, 4, 30)
    assert trend[-1].calories == 2000
    assert trend[-1].deviation == 0
    assert trend[-1].moving_avg_calories is not None
    assert pytest.approx(trend[-1].moving_avg_calories) == 1900.0


def test_progress_bar_caps_fill_at_100_but_shows_true_percent() -> None:
    """Bar width caps at 100% while label can exceed for over-target days."""
    bar = format_progress_bar(130.0)
    assert "130%" in bar
    assert bar.startswith("[")
    assert "█" in bar
