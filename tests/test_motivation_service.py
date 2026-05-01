"""Unit tests for MotivationService rate limits and first-meal trigger."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from calorie_bot.app.domain import MealSource, MotivationEventType
from calorie_bot.app.messages import motivation as motivation_texts
from calorie_bot.app.services.motivation_service import MotivationService

TZ = ZoneInfo("Europe/Moscow")
FIXED_NOW = datetime(2026, 4, 30, 14, 0, tzinfo=TZ)


class FakeStatsRepository:
    """Minimal stats repo: single meal list for any in-range query."""

    def __init__(self, meals: list) -> None:
        self._meals = meals

    async def list_confirmed_meals_between(
        self,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list:
        """Return meals in ``[start_at, end_at)`` for the user."""
        out: list = []
        for meal in self._meals:
            if getattr(meal, "user_id", 1) != user_id:
                continue
            eaten = meal.eaten_at
            if eaten.tzinfo is None:
                eaten = eaten.replace(tzinfo=start_at.tzinfo)
            if start_at <= eaten < end_at:
                out.append(meal)
        return out


class FakeMealRepository:
    """Return a fixed confirmed meal count."""

    def __init__(self, total_confirmed: int) -> None:
        self._count = total_confirmed

    async def count_confirmed_meals(self, user_id: int) -> int:
        """Return preconfigured count."""
        return self._count


class FakeMotivationEventRepository:
    """In-memory motivation events for cooldown and idempotency checks."""

    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    async def create_event(
        self,
        user_id: int,
        event_type: str,
        event_date: datetime,
        payload: dict | None = None,
    ) -> SimpleNamespace:
        """Record a motivation event."""
        row = SimpleNamespace(
            user_id=user_id,
            event_type=event_type,
            event_date=event_date,
            payload=payload,
        )
        self.events.append(row)
        return row

    async def count_since(self, user_id: int, since: datetime) -> int:
        """Count events at or after ``since``."""
        n = 0
        for e in self.events:
            if e.user_id != user_id:
                continue
            if e.event_date >= since:
                n += 1
        return n

    async def last_event_of_type(self, user_id: int, event_type: str):
        """Most recent matching event."""
        latest = None
        for e in self.events:
            if e.user_id != user_id or e.event_type != event_type:
                continue
            if latest is None or e.event_date > latest.event_date:
                latest = e
        return latest

    async def has_ever_event_type(self, user_id: int, event_type: str) -> bool:
        """True if any event of this type exists."""
        return await self.last_event_of_type(user_id, event_type) is not None


class FakeProfileRepository:
    """Profile with targets and timezone."""

    def __init__(self) -> None:
        pass

    async def get_by_user_id(self, user_id: int):
        """Return namespace with fields MotivationService reads."""
        return SimpleNamespace(
            daily_calorie_target=2000,
            timezone="Europe/Moscow",
        )


class FakeSettingsRepository:
    """Optional UserSettings row."""

    def __init__(self, motivation_messages_enabled: bool | None) -> None:
        self._motivation = motivation_messages_enabled

    async def get_by_user_id(self, user_id: int):
        """``None`` means row missing (treat as motivation on in service)."""
        if self._motivation is None:
            return None
        return SimpleNamespace(motivation_messages_enabled=self._motivation)


def _meal(
    user_id: int,
    eaten_at: datetime,
    *,
    calories: int = 400,
    source: str = MealSource.TEXT.value,
) -> SimpleNamespace:
    """One confirmed meal row."""
    return SimpleNamespace(
        user_id=user_id,
        eaten_at=eaten_at,
        total_calories=calories,
        source=source,
    )


def _service(
    meals: list,
    total_confirmed: int,
    motivation_repo: FakeMotivationEventRepository,
    *,
    settings_motivation: bool | None = True,
) -> MotivationService:
    """Assemble MotivationService with fake dependencies."""
    return MotivationService(
        FakeStatsRepository(meals),
        FakeMealRepository(total_confirmed),
        motivation_repo,
        FakeProfileRepository(),
        FakeSettingsRepository(settings_motivation),
        "Europe/Moscow",
        now_factory=lambda _tz: FIXED_NOW,
    )


@pytest.mark.asyncio
async def test_motivation_disabled_returns_none() -> None:
    """When user turned motivation off, emit nothing."""
    meal = _meal(1, datetime(2026, 4, 30, 10, 0, tzinfo=TZ))
    svc = _service([meal], 1, FakeMotivationEventRepository(), settings_motivation=False)
    out = await svc.maybe_emit(1, "meal_save", meal_was_new=True)
    assert out is None


@pytest.mark.asyncio
async def test_first_saved_meal_message() -> None:
    """Exactly one confirmed meal and new save triggers first-meal copy."""
    meal = _meal(1, datetime(2026, 4, 30, 10, 0, tzinfo=TZ))
    mot = FakeMotivationEventRepository()
    svc = _service([meal], 1, mot)
    out = await svc.maybe_emit(1, "meal_save", meal_was_new=True)
    assert out == motivation_texts.MESSAGES[MotivationEventType.FIRST_SAVED_MEAL]
    assert len(mot.events) == 1
    assert mot.events[0].event_type == MotivationEventType.FIRST_SAVED_MEAL.value


@pytest.mark.asyncio
async def test_first_saved_meal_not_repeated() -> None:
    """Same state after logging first_saved_meal does not send duplicate."""
    meal = _meal(1, datetime(2026, 4, 30, 10, 0, tzinfo=TZ))
    mot = FakeMotivationEventRepository()
    svc = _service([meal], 1, mot)
    first = await svc.maybe_emit(1, "meal_save", meal_was_new=True)
    assert first is not None
    second = await svc.maybe_emit(1, "meal_save", meal_was_new=True)
    assert second is None
    assert len(mot.events) == 1
