"""Optional in-process TTL cache for hot read paths (no Redis required)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from calorie_bot.app.storage.dto import DailyAggregateDTO
from calorie_bot.app.storage.interface import StorageInterface


@dataclass
class _CacheEntry:
    """Single cached aggregate with expiry."""

    value: DailyAggregateDTO | None
    expires_at: float


class CachingStorageWrapper:
    """Delegate ``StorageInterface`` and cache ``get_daily_aggregates`` only."""

    def __init__(self, inner: StorageInterface, ttl_seconds: float) -> None:
        """Wrap ``inner``; ``ttl_seconds <= 0`` disables caching."""
        self._inner = inner
        # __getattr__ is not used by type checkers; explicit passthrough:
        self._ttl = ttl_seconds
        self._cache: dict[tuple[int, date], _CacheEntry] = {}

    async def save_meal(self, meal: Any) -> Any:
        return await self._inner.save_meal(meal)

    async def save_meals_batch(self, meals: list[Any]) -> list[Any]:
        return await self._inner.save_meals_batch(meals)

    async def get_meals_by_day(self, user_id: int, day: date, *, tz_name: str) -> list[Any]:
        return await self._inner.get_meals_by_day(user_id, day, tz_name=tz_name)

    async def get_meals_range(self, user_id: int, start: Any, end: Any) -> list[Any]:
        return await self._inner.get_meals_range(user_id, start, end)

    async def delete_meal(self, meal_id: int, user_id: int) -> bool:
        return await self._inner.delete_meal(meal_id, user_id)

    async def get_user_settings(self, user_id: int) -> Any:
        return await self._inner.get_user_settings(user_id)

    async def save_user_settings(self, user_id: int, settings: Any) -> None:
        await self._inner.save_user_settings(user_id, settings)

    async def get_daily_aggregates(self, user_id: int, day: date) -> DailyAggregateDTO | None:
        """Return cached aggregate when TTL > 0 and entry is still valid."""
        if self._ttl <= 0:
            return await self._inner.get_daily_aggregates(user_id, day)
        key = (user_id, day)
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and hit.expires_at > now:
            return hit.value
        value = await self._inner.get_daily_aggregates(user_id, day)
        self._cache[key] = _CacheEntry(value=value, expires_at=now + self._ttl)
        return value

    async def get_range_aggregates(
        self,
        user_id: int,
        start_day: date,
        end_day: date,
    ) -> list[DailyAggregateDTO]:
        return await self._inner.get_range_aggregates(user_id, start_day, end_day)
