"""Rolling calorie trends (separate from calendar StatsService)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from calorie_bot.app.database.models import Meal
from calorie_bot.app.domain import (
    FitnessGoal,
    MealSource,
    TrendDayPoint,
    TrendProductFreq,
    TrendReport,
    TrendSourceSlice,
)
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository
from calorie_bot.app.services.calorie_service import normalize_food_name

_VALID_WINDOWS = frozenset({7, 14, 30})

_SOURCE_LABELS: dict[str, str] = {
    MealSource.PHOTO.value: "фото",
    MealSource.TEXT.value: "текст",
    MealSource.AUDIO.value: "голос",
    MealSource.MIXED.value: "с правками",
    MealSource.MANUAL.value: "вручную",
}

_WEEKDAY_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


class TrendService:
    """Build rolling-window trend reports using ``StatsRepository`` reads."""

    def __init__(
        self,
        stats_repository: StatsRepository,
        profile_repository: ProfileRepository,
        default_timezone: str,
        *,
        now_factory: Callable[[ZoneInfo], datetime] | None = None,
    ) -> None:
        """Wire repositories; optional ``now_factory`` fixes time in tests."""
        self._stats_repository = stats_repository
        self._profile_repository = profile_repository
        self._default_timezone = default_timezone
        self._now = now_factory or (lambda tz: datetime.now(tz))

    async def build_report(self, user_id: int, window_days: int) -> TrendReport:
        """Aggregate calories, sources, and foods for the last ``window_days`` (today included)."""
        if window_days not in _VALID_WINDOWS:
            raise ValueError("trend_window_must_be_7_14_or_30")

        tz = await self._user_tz(user_id)
        now = self._now(tz)
        today = now.date()
        current_start = today - timedelta(days=window_days - 1)

        range_start = datetime.combine(current_start, time.min, tzinfo=tz)
        range_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)

        prev_end_date = current_start - timedelta(days=1)
        prev_start_date = prev_end_date - timedelta(days=window_days - 1)
        prev_start = datetime.combine(prev_start_date, time.min, tzinfo=tz)
        prev_end = datetime.combine(prev_end_date + timedelta(days=1), time.min, tzinfo=tz)

        meals_now = await self._stats_repository.list_confirmed_meals_between(
            user_id,
            range_start,
            range_end,
        )
        meals_prev = await self._stats_repository.list_confirmed_meals_between(
            user_id,
            prev_start,
            prev_end,
        )

        profile = await self._profile_repository.get_by_user_id(user_id)
        target = profile.daily_calorie_target if profile else None
        goal_key = profile.goal if profile else None
        goal_enum = _parse_goal(goal_key)

        by_day_now = _sum_calories_by_local_date(meals_now, tz)
        by_day_prev = _sum_calories_by_local_date(meals_prev, tz)

        current_dates = _dates_inclusive(current_start, today)
        prev_dates = _dates_inclusive(prev_start_date, prev_end_date)

        daily_points = tuple(
            TrendDayPoint(day_label=_ru_day_label(d), calories=by_day_now.get(d, 0))
            for d in current_dates
        )

        total_now = sum(by_day_now.get(d, 0) for d in current_dates)
        avg_now = total_now / window_days

        total_prev = sum(by_day_prev.get(d, 0) for d in prev_dates)
        avg_prev = total_prev / window_days if window_days > 0 else None

        change_pct = None
        if avg_prev is not None and avg_prev > 0:
            change_pct = 100.0 * (avg_now - avg_prev) / avg_prev

        days_with_logs = sum(1 for d in current_dates if by_day_now.get(d, 0) > 0)
        days_without = window_days - days_with_logs
        empty_labels = tuple(_ru_day_label(d) for d in current_dates if by_day_now.get(d, 0) == 0)

        regularity = 100.0 * days_with_logs / window_days if window_days else 0.0

        aligned_now = _count_soft_goal_days(by_day_now, current_dates, target, goal_enum)
        aligned_prev = _count_soft_goal_days(by_day_prev, prev_dates, target, goal_enum)

        top_products = tuple(
            TrendProductFreq(display_name=name, times_seen=cnt)
            for name, cnt in _top_products(meals_now, limit=5)
        )

        source_slices = tuple(_source_breakdown(meals_now))

        interpretation = _interpret_lines(
            window_days=window_days,
            avg_now=avg_now,
            avg_prev=avg_prev,
            change_pct=change_pct,
            target=target,
            aligned_now=aligned_now,
            days_with_logs=days_with_logs,
            days_without=days_without,
            regularity_percent=regularity,
            aligned_prev=aligned_prev,
            prev_days_with_logs=sum(1 for d in prev_dates if by_day_prev.get(d, 0) > 0),
        )

        return TrendReport(
            window_days=window_days,
            calorie_target=target,
            fitness_goal_key=goal_key,
            daily_points=daily_points,
            avg_calories_per_calendar_day=avg_now,
            previous_window_avg=avg_prev,
            avg_change_vs_prev_percent=change_pct,
            days_with_logs=days_with_logs,
            days_without_logs=days_without,
            empty_day_labels=empty_labels,
            regularity_percent=regularity,
            goal_relaxed_match_days=aligned_now,
            top_products=top_products,
            source_slices=source_slices,
            interpretation_lines=interpretation,
        )

    async def _user_tz(self, user_id: int) -> ZoneInfo:
        """Resolve IANA timezone: profile → app default."""
        profile = await self._profile_repository.get_by_user_id(user_id)
        tz_name = profile.timezone if profile and profile.timezone else self._default_timezone
        return ZoneInfo(tz_name)


def _parse_goal(raw: str | None) -> FitnessGoal | None:
    if not raw:
        return None
    try:
        return FitnessGoal(raw)
    except ValueError:
        return None


def _meal_local_date(meal: Meal, tz: ZoneInfo) -> date:
    eaten = meal.eaten_at
    if eaten.tzinfo is None:
        eaten = eaten.replace(tzinfo=tz)
    return eaten.astimezone(tz).date()


def _sum_calories_by_local_date(meals: list[Meal], tz: ZoneInfo) -> dict[date, int]:
    totals: dict[date, int] = defaultdict(int)
    for meal in meals:
        totals[_meal_local_date(meal, tz)] += meal.total_calories
    return dict(totals)


def _dates_inclusive(start: date, end: date) -> tuple[date, ...]:
    days = (end - start).days + 1
    return tuple(start + timedelta(days=i) for i in range(days))


def _ru_day_label(d: date) -> str:
    return f"{_WEEKDAY_RU[d.weekday()]} {d.day:02d}.{d.month:02d}"


def _soft_goal_match(calories: int, target: int, goal: FitnessGoal | None) -> bool:
    """Inclusive band around target; avoids harsh pass/fail wording in copy."""
    band = max(80, int(target * 0.10))
    if goal == FitnessGoal.LOSE_WEIGHT:
        return calories <= target + band
    if goal == FitnessGoal.GAIN_WEIGHT:
        return calories >= target - band
    return abs(calories - target) <= band


def _count_soft_goal_days(
    by_day: dict[date, int],
    dates: tuple[date, ...],
    target: int | None,
    goal: FitnessGoal | None,
) -> int:
    if target is None or target <= 0:
        return 0
    count = 0
    for d in dates:
        kcal = by_day.get(d, 0)
        if kcal <= 0:
            continue
        if _soft_goal_match(kcal, target, goal):
            count += 1
    return count


def _top_products(meals: list[Meal], limit: int) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    display: dict[str, str] = {}
    for meal in meals:
        for item in meal.items:
            key = normalize_food_name(item.name)
            counter[key] += 1
            display.setdefault(key, item.name.strip())
    top = counter.most_common(limit)
    return [(display.get(k, k), c) for k, c in top]


def _source_breakdown(meals: list[Meal]) -> list[TrendSourceSlice]:
    if not meals:
        return []
    counts = Counter(m.source for m in meals)
    total = len(meals)
    slices: list[TrendSourceSlice] = []
    for key, cnt in counts.most_common():
        label = _SOURCE_LABELS.get(key, "другое")
        pct = 100.0 * cnt / total
        slices.append(
            TrendSourceSlice(
                source_key=key,
                display_label=label,
                meal_count=cnt,
                percent=pct,
            )
        )
    return slices


def _interpret_lines(
    *,
    window_days: int,
    avg_now: float,
    avg_prev: float | None,
    change_pct: float | None,
    target: int | None,
    aligned_now: int,
    days_with_logs: int,
    days_without: int,
    regularity_percent: float,
    aligned_prev: int | None,
    prev_days_with_logs: int,
) -> tuple[str, ...]:
    """Short, neutral copy — observations only, no shame or toxic motivation."""
    lines: list[str] = []

    if (
        aligned_prev is not None
        and prev_days_with_logs > 0
        and days_with_logs > 0
        and aligned_now > aligned_prev
    ):
        lines.append(
            "По сравнению с прошлым таким же отрезком чаще получалось оставаться "
            "ближе к мягкому ориентиру по калориям."
        )

    if avg_prev is not None:
        if avg_prev > 0 and change_pct is not None:
            if abs(change_pct) < 5:
                lines.append(
                    "Среднесуточные калории почти на том же уровне, что и на прошлом отрезке."
                )
            elif change_pct > 0:
                lines.append(
                    "Средняя калорийность немного выросла к прошлому периоду — "
                    "это просто наблюдение, без оценки."
                )
            else:
                lines.append(
                    "Средняя калорийность немного ниже, чем на прошлом отрезке — "
                    "так тоже бывает."
                )
        elif avg_prev == 0 and avg_now > 0:
            lines.append(
                "На прошлом отрезке почти не было записей — сейчас проще сравнивать дни."
            )

    if target and days_with_logs > 0:
        lines.append(
            f"В {aligned_now} из {days_with_logs} дней с записями калории вписывались "
            "в мягкий коридор вокруг твоего ориентира."
        )
    elif target is None and days_with_logs > 0:
        lines.append(
            "Дневной ориентир по калориям не задан — для «к цели» полезно указать цель в профиле."
        )

    if days_without > 0:
        if days_without <= 3:
            lines.append(
                f"{days_without} дн. без записей — при желании можно дополнить позже, без спешки."
            )
        else:
            lines.append(
                "Были дни без записей: это нормально. Можно вести дневник в своём темпе, "
                "когда удобно."
            )

    if regularity_percent >= 85 and window_days >= 7:
        lines.append("Записи по дням довольно ровные — удобно смотреть динамику.")
    elif regularity_percent < 45 and window_days >= 14:
        lines.append(
            "Записей меньше половины дней — график всё равно показывает то, что уже есть."
        )

    if not lines:
        lines.append("Пока мало данных — как накопятся дни, тренды станут говорительнее.")

    return tuple(lines[:6])
