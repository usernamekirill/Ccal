"""Emit rare, opt-in motivational messages after saves and on stats views."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.database.models import Meal
from calorie_bot.app.domain import MealSource, MotivationEventType
from calorie_bot.app.messages import motivation as motivation_texts
from calorie_bot.app.repositories.meal_repository import MealRepository
from calorie_bot.app.repositories.motivation_event_repository import MotivationEventRepository
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.repositories.settings_repository import SettingsRepository
from calorie_bot.app.repositories.stats_repository import StatsRepository

MotivationContext = Literal["meal_save", "stats"]


class MotivationService:
    """Decide when to show motivational text and log ``motivation_events``."""

    def __init__(
        self,
        stats_repository: StatsRepository,
        meal_repository: MealRepository,
        motivation_event_repository: MotivationEventRepository,
        profile_repository: ProfileRepository,
        settings_repository: SettingsRepository,
        default_timezone: str,
        *,
        now_factory: Callable[[ZoneInfo], datetime] | None = None,
    ) -> None:
        self._stats = stats_repository
        self._meals = meal_repository
        self._motivation = motivation_event_repository
        self._profile = profile_repository
        self._settings = settings_repository
        self._default_timezone = default_timezone
        self._now = now_factory or (lambda tz: datetime.now(tz))

    async def maybe_emit(
        self,
        user_id: int,
        context: MotivationContext,
        *,
        meal_was_new: bool = False,
    ) -> str | None:
        """Return one short message and log it, or ``None`` if skipped."""
        settings = await self._settings.get_by_user_id(user_id)
        if settings is not None and settings.motivation_messages_enabled is False:
            return None

        profile = await self._profile.get_by_user_id(user_id)
        tz_name = profile.timezone if profile and profile.timezone else self._default_timezone
        tz = ZoneInfo(tz_name)
        now = self._now(tz)
        today = now.date()

        target = profile.daily_calorie_target if profile else None

        window_start = datetime.combine(today - timedelta(days=89), time.min, tzinfo=tz)
        window_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)
        recent_meals = await self._stats.list_confirmed_meals_between(
            user_id, window_start, window_end
        )
        logged_days = _logged_dates(recent_meals, tz)
        streak = _streak_from_today(logged_days, today)
        gap_before = _empty_run_before(today, logged_days)

        total_confirmed = await self._meals.count_confirmed_meals(user_id)

        day_start = datetime.combine(today, time.min, tzinfo=tz)
        day_meals = await self._stats.list_confirmed_meals_between(
            user_id,
            day_start,
            window_end,
        )
        today_cals = sum(m.total_calories for m in day_meals)

        last7_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=tz)
        prev7_start = datetime.combine(today - timedelta(days=13), time.min, tzinfo=tz)
        prev7_end = datetime.combine(today - timedelta(days=6), time.min, tzinfo=tz)

        meals_last7 = await self._stats.list_confirmed_meals_between(
            user_id, last7_start, window_end
        )
        meals_prev7 = await self._stats.list_confirmed_meals_between(
            user_id, prev7_start, prev7_end
        )

        dates_last7 = _days_in_range(today - timedelta(days=6), today)
        dates_prev7 = _days_in_range(today - timedelta(days=13), today - timedelta(days=7))
        logged_last7 = _logged_dates(meals_last7, tz)
        logged_prev7 = _logged_dates(meals_prev7, tz)
        rate_last7 = sum(1 for d in dates_last7 if d in logged_last7) / 7.0
        rate_prev7 = sum(1 for d in dates_prev7 if d in logged_prev7) / 7.0

        photo_share = _photo_share(meals_last7)
        close_to_goal = _is_close_to_goal(today_cals, target)

        candidates: list[tuple[int, MotivationEventType]] = []

        if context == "meal_save" and meal_was_new:
            if total_confirmed == 1:
                candidates.append((1, MotivationEventType.FIRST_SAVED_MEAL))
            if (
                gap_before >= 5
                and total_confirmed >= 2
                and today in logged_days
            ):
                candidates.append((2, MotivationEventType.RETURNED_AFTER_BREAK))

        if streak >= 7:
            candidates.append((3, MotivationEventType.STREAK_7_DAYS))
        elif streak == 3:
            candidates.append((4, MotivationEventType.STREAK_3_DAYS))

        if close_to_goal and target:
            candidates.append((5, MotivationEventType.CLOSE_TO_GOAL))

        if (
            rate_last7 - rate_prev7 >= 0.14
            and rate_prev7 <= 0.86
            and sum(1 for d in dates_prev7 if d in logged_prev7) > 0
        ):
            candidates.append((6, MotivationEventType.REGULARITY_IMPROVED))

        if len(meals_last7) >= 4 and photo_share >= 0.65:
            candidates.append((7, MotivationEventType.PHOTO_ENTHUSIAST))

        candidates.sort(key=lambda x: x[0])

        for _prio, event_type in candidates:
            if context == "stats" and event_type in (
                MotivationEventType.FIRST_SAVED_MEAL,
                MotivationEventType.RETURNED_AFTER_BREAK,
            ):
                continue

            if event_type == MotivationEventType.PHOTO_ENTHUSIAST and photo_share < 0.65:
                continue

            if event_type == MotivationEventType.CLOSE_TO_GOAL and not close_to_goal:
                continue

            if event_type == MotivationEventType.STREAK_7_DAYS and streak < 7:
                continue

            if event_type == MotivationEventType.STREAK_3_DAYS and streak != 3:
                continue

            if event_type == MotivationEventType.RETURNED_AFTER_BREAK and gap_before < 5:
                continue

            if not await self._passes_type_cooldown(user_id, event_type, now):
                continue

            bypass_global = event_type == MotivationEventType.FIRST_SAVED_MEAL
            if not await self._passes_global_limits(user_id, now, tz, bypass_global):
                continue

            if event_type == MotivationEventType.FIRST_SAVED_MEAL:
                if await self._motivation.has_ever_event_type(
                    user_id, MotivationEventType.FIRST_SAVED_MEAL.value
                ):
                    continue

            msg = motivation_texts.MESSAGES[event_type]
            await self._motivation.create_event(
                user_id,
                event_type.value,
                now,
                {"context": context},
            )
            return msg

        return None

    async def _passes_global_limits(
        self,
        user_id: int,
        now: datetime,
        tz: ZoneInfo,
        bypass_interval: bool,
    ) -> bool:
        """Cap messages per day and minimum spacing (first meal can bypass spacing)."""
        day_start = datetime.combine(now.date(), time.min, tzinfo=tz)
        today_count = await self._motivation.count_since(user_id, day_start)
        if today_count >= motivation_texts.GLOBAL_MAX_PER_LOCAL_DAY:
            return False
        if bypass_interval:
            return True
        since = now - timedelta(hours=motivation_texts.GLOBAL_MIN_HOURS_BETWEEN)
        recent = await self._motivation.count_since(user_id, since)
        return recent == 0

    async def _passes_type_cooldown(
        self,
        user_id: int,
        event_type: MotivationEventType,
        now: datetime,
    ) -> bool:
        """Enforce per-type quiet period."""
        hours = motivation_texts.TYPE_COOLDOWN_HOURS.get(event_type)
        if hours is None:
            return True
        last = await self._motivation.last_event_of_type(user_id, event_type.value)
        if last is None:
            return True
        delta = now - last.event_date
        if delta.total_seconds() < 0:
            return True
        return delta >= timedelta(hours=hours)


def create_motivation_service(session: AsyncSession, app_settings: Settings) -> MotivationService:
    """Build a ``MotivationService`` for the current request."""
    return MotivationService(
        StatsRepository(session),
        MealRepository(session),
        MotivationEventRepository(session),
        ProfileRepository(session),
        SettingsRepository(session),
        app_settings.timezone,
    )


def _logged_dates(meals: list[Meal], tz: ZoneInfo) -> set[date]:
    """Collect local calendar dates that have at least one meal."""
    out: set[date] = set()
    for meal in meals:
        out.add(_meal_local_date(meal, tz))
    return out


def _meal_local_date(meal: Meal, tz: ZoneInfo) -> date:
    eaten = meal.eaten_at
    if eaten.tzinfo is None:
        eaten = eaten.replace(tzinfo=tz)
    return eaten.astimezone(tz).date()


def _streak_from_today(logged: set[date], today: date) -> int:
    streak = 0
    d = today
    while d in logged:
        streak += 1
        d -= timedelta(days=1)
    return streak


def _empty_run_before(today: date, logged: set[date], max_scan: int = 60) -> int:
    """Count consecutive empty local days immediately before ``today``."""
    d = today - timedelta(days=1)
    n = 0
    while n < max_scan and d not in logged:
        n += 1
        d -= timedelta(days=1)
    return n


def _days_in_range(start: date, end: date) -> tuple[date, ...]:
    span = (end - start).days + 1
    return tuple(start + timedelta(days=i) for i in range(span))


def _photo_share(meals: list[Meal]) -> float:
    if not meals:
        return 0.0
    photo_n = sum(1 for m in meals if m.source == MealSource.PHOTO.value)
    return photo_n / len(meals)


def _is_close_to_goal(today_cals: int, target: int | None) -> bool:
    if target is None or target <= 0:
        return False
    diff = abs(today_cals - target)
    band_kcal = max(120, int(target * 0.12))
    return diff <= band_kcal
