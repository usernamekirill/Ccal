"""Aggregate nutrition statistics by calendar periods in the user's timezone."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

from calorie_bot.app.database.models import Meal
from calorie_bot.app.domain import (
    CalorieTrendPoint,
    StatsMonthView,
    StatsTodayView,
    StatsWeekView,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.stats.charting import NullStatsChartRenderer, StatsChartRenderer


class StatsService:
    """Calculate local nutrition statistics without AI calls."""

    def __init__(
        self,
        stats_repository: StatsRepository,
        profile_repository: ProfileRepository,
        default_timezone: str,
        chart_renderer: StatsChartRenderer | None = None,
        *,
        now_factory: Callable[[ZoneInfo], datetime] | None = None,
    ) -> None:
        self._stats_repository = stats_repository
        self._profile_repository = profile_repository
        self._default_timezone = default_timezone
        self._charts = chart_renderer or NullStatsChartRenderer()
        self._now = now_factory or (lambda tz: datetime.now(tz))

    async def today_view(self, user_id: int) -> StatsTodayView:
        """Return today's calories, targets, progress, and food listing."""
        tz = await self._user_tz(user_id)
        now = self._now(tz)
        start, end = _day_bounds(now.date(), tz)
        meals = await self._stats_repository.list_confirmed_meals_between(user_id, start, end)
        profile = await self._profile_repository.get_by_user_id(user_id)
        target = profile.daily_calorie_target if profile else None

        total = sum(m.total_calories for m in meals)
        remaining = (target - total) if target is not None else None
        progress = (100.0 * total / target) if target and target > 0 else None

        t_lo = sum(
            m.total_calories_min if m.total_calories_min is not None else m.total_calories
            for m in meals
        )
        t_hi = sum(
            m.total_calories_max if m.total_calories_max is not None else m.total_calories
            for m in meals
        )
        has_calorie_band = bool(meals) and t_lo != t_hi
        estimated_ratio = (
            sum(1 for m in meals if getattr(m, "has_estimated_items", False)) / len(meals)
            if meals
            else None
        )

        sections = _meal_food_sections(meals, tz)
        has_approx = any(getattr(m, "has_estimated_items", False) for m in meals) or (
            estimated_ratio is not None and estimated_ratio > 0
        )
        total_protein = (
            sum(float(getattr(m, "total_protein_g", None) or 0) for m in meals) if meals else None
        )
        total_fat = sum(float(getattr(m, "total_fat_g", None) or 0) for m in meals) if meals else None
        total_carbs = (
            sum(float(getattr(m, "total_carbs_g", None) or 0) for m in meals) if meals else None
        )
        pt = getattr(profile, "daily_protein_target_g", None) if profile else None
        ft = getattr(profile, "daily_fat_target_g", None) if profile else None
        ct = getattr(profile, "daily_carbs_target_g", None) if profile else None
        return StatsTodayView(
            total_calories=total,
            calorie_target=target,
            remaining_kcal=remaining,
            progress_percent=progress,
            meals_count=len(meals),
            food_sections=sections,
            has_approximate_values=has_approx,
            total_calories_min=t_lo if has_calorie_band else None,
            total_calories_max=t_hi if has_calorie_band else None,
            estimated_meals_ratio=estimated_ratio,
            total_protein_g=round(total_protein, 1) if total_protein is not None else None,
            total_fat_g=round(total_fat, 1) if total_fat is not None else None,
            total_carbs_g=round(total_carbs, 1) if total_carbs is not None else None,
            protein_target_g=pt,
            fat_target_g=ft,
            carbs_target_g=ct,
        )

    async def week_view(self, user_id: int) -> StatsWeekView:
        """Return Mon–Sun window stats in the user's timezone."""
        tz = await self._user_tz(user_id)
        now = self._now(tz)
        today = now.date()
        monday = today - timedelta(days=today.weekday())
        week_start = datetime.combine(monday, time.min, tzinfo=tz)
        week_end = week_start + timedelta(days=7)
        meals = await self._stats_repository.list_confirmed_meals_between(
            user_id,
            week_start,
            week_end,
        )
        profile = await self._profile_repository.get_by_user_id(user_id)
        target = profile.daily_calorie_target if profile else None

        by_day = _sum_meals_by_local_date(meals, tz)
        week_days = [monday + timedelta(days=i) for i in range(7)]
        daily_totals = [(d, by_day.get(d, 0)) for d in week_days]

        total_week = sum(c for _, c in daily_totals)
        avg_per_day = total_week / 7.0

        days_with_logs = sum(1 for _, c in daily_totals if c > 0)
        days_above = 0
        days_below_eq = 0
        if target is not None:
            for _, cals in daily_totals:
                if cals == 0:
                    continue
                if cals > target:
                    days_above += 1
                else:
                    days_below_eq += 1

        best_label, best_cals, best_delta = _best_adherence_day(daily_totals, target)

        _ = self._charts.build_week_calories(user_id, daily_totals)

        return StatsWeekView(
            avg_calories_per_day=avg_per_day if days_with_logs else None,
            days_above_target=days_above,
            days_below_or_equal_target=days_below_eq,
            days_with_logs=days_with_logs,
            calendar_days_in_window=7,
            best_day_label=best_label,
            best_day_calories=best_cals,
            best_day_delta_from_target=best_delta,
            calorie_target=target,
        )

    async def month_view(self, user_id: int) -> StatsMonthView:
        """Return month-to-date stats and a simple intra-month trend."""
        tz = await self._user_tz(user_id)
        now = self._now(tz)
        month_start = now.date().replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        start = datetime.combine(month_start, time.min, tzinfo=tz)
        end = datetime.combine(next_month, time.min, tzinfo=tz)

        meals = await self._stats_repository.list_confirmed_meals_between(user_id, start, end)
        profile = await self._profile_repository.get_by_user_id(user_id)
        target = profile.daily_calorie_target if profile else None

        by_day = _sum_meals_by_local_date(meals, tz)

        today = now.date()
        last_calendar_day = next_month - timedelta(days=1)
        month_last = min(today, last_calendar_day)
        days_elapsed = (month_last - month_start).days + 1

        total_cals = sum(by_day.values())
        avg_per_day = (total_cals / days_elapsed) if days_elapsed > 0 else None

        days_with_data = len(by_day)
        regularity = (100.0 * days_with_data / days_elapsed) if days_elapsed > 0 else None

        trend = _month_trend_label(list(by_day.items()))

        return StatsMonthView(
            avg_calories_per_day=avg_per_day,
            trend_label=trend,
            days_with_data=days_with_data,
            days_elapsed_in_month=days_elapsed,
            regularity_percent=regularity,
            calorie_target=target,
        )

    async def get_calorie_trend(
        self,
        user_id: int,
        *,
        window_days: int = 14,
        moving_avg_window: int = 3,
    ) -> list[CalorieTrendPoint]:
        """Return daily calories, goal deviation, and simple moving average (one meal query)."""
        tz = await self._user_tz(user_id)
        now = self._now(tz)
        end_date = now.date()
        start_date = end_date - timedelta(days=window_days - 1)
        start_dt = datetime.combine(start_date, time.min, tzinfo=tz)
        end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
        meals = await self._stats_repository.list_confirmed_meals_between(
            user_id,
            start_dt,
            end_dt,
        )
        by_day = _sum_meals_by_local_date(meals, tz)
        profile = await self._profile_repository.get_by_user_id(user_id)
        target = profile.daily_calorie_target if profile else None

        raw: list[CalorieTrendPoint] = []
        for i in range(window_days):
            d = start_date + timedelta(days=i)
            cal = by_day.get(d, 0)
            deviation = (cal - target) if target is not None else None
            raw.append(
                CalorieTrendPoint(
                    day=d,
                    calories=cal,
                    calorie_goal=target,
                    deviation=deviation,
                    moving_avg_calories=None,
                )
            )

        out: list[CalorieTrendPoint] = []
        for i, p in enumerate(raw):
            lo = max(0, i - moving_avg_window + 1)
            window_slice = raw[lo : i + 1]
            avg = sum(x.calories for x in window_slice) / len(window_slice)
            out.append(
                CalorieTrendPoint(
                    day=p.day,
                    calories=p.calories,
                    calorie_goal=p.calorie_goal,
                    deviation=p.deviation,
                    moving_avg_calories=avg,
                )
            )
        return out

    async def _user_tz(self, user_id: int) -> ZoneInfo:
        """Resolve IANA timezone: profile → default app setting."""
        profile = await self._profile_repository.get_by_user_id(user_id)
        tz_name = profile.timezone if profile and profile.timezone else self._default_timezone
        return ZoneInfo(tz_name)


def _day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Return ``[start, end)`` aware datetimes for a local calendar day."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def _meal_local_date(meal: Meal, tz: ZoneInfo) -> date:
    """Normalize meal timestamp to a calendar date in ``tz``."""
    eaten = meal.eaten_at
    if eaten.tzinfo is None:
        eaten = eaten.replace(tzinfo=tz)
    return eaten.astimezone(tz).date()


def _sum_meals_by_local_date(meals: list[Meal], tz: ZoneInfo) -> dict[date, int]:
    """Sum calories and meal counts per local calendar day."""
    totals: dict[date, int] = defaultdict(int)
    for meal in meals:
        totals[_meal_local_date(meal, tz)] += meal.total_calories
    return dict(totals)


def _meal_food_sections(meals: list[Meal], tz: ZoneInfo) -> list[str]:
    """Build Telegram lines: time — meal total; indented items."""
    lines: list[str] = []
    for meal in sorted(meals, key=lambda m: m.eaten_at):
        eaten = meal.eaten_at
        if eaten.tzinfo is None:
            eaten = eaten.replace(tzinfo=tz)
        local_t = eaten.astimezone(tz)
        lines.append(f"• {local_t.strftime('%H:%M')} — {meal.total_calories} ккал")
        for item in meal.items:
            lines.append(f"  ◦ {item.name} — {item.calories} ккал")
    return lines


def _best_adherence_day(
    day_totals: list[tuple[date, int]],
    target: int | None,
) -> tuple[str | None, int | None, int | None]:
    """Pick the day closest to calorie target (smallest absolute delta)."""
    logged = [(d, c) for d, c in day_totals if c > 0]
    if not logged or target is None:
        return None, None, None
    day, cals = min(logged, key=lambda dc: abs(dc[1] - target))
    return _ru_weekday_caption(day), cals, cals - target


def _ru_weekday_caption(day: date) -> str:
    """Short Russian weekday + date for display."""
    names = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    return f"{names[day.weekday()]} {day.day:02d}.{day.month:02d}"


def _month_trend_label(day_totals: list[tuple[date, int]]) -> str:
    """Compare first vs second half of logged days in the month (no graphics)."""
    if len(day_totals) < 4:
        return "мало данных"
    ordered = sorted(day_totals, key=lambda x: x[0])
    calories_only = [c for _, c in ordered]
    mid = len(calories_only) // 2
    first_avg = mean(calories_only[:mid])
    second_avg = mean(calories_only[mid:])
    if second_avg > first_avg * 1.05:
        return "растёт"
    if second_avg < first_avg * 0.95:
        return "снижается"
    return "стабильно"
