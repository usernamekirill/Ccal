"""Storage abstraction: any backend (SQLite, Postgres, HTTP) implements this protocol."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from calorie_bot.app.storage.dto import DailyAggregateDTO, MealDTO, UserSettingsDTO


@runtime_checkable
class StorageInterface(Protocol):
    """Async storage port. No SQLAlchemy types on the surface."""

    async def save_meal(self, meal: MealDTO) -> MealDTO:
        """Insert or replace a meal graph (items included). Returns DTO with id."""

    async def save_meals_batch(self, meals: list[MealDTO]) -> list[MealDTO]:
        """Batch persist meals (single transaction / round-trip where possible)."""

    async def get_meals_by_day(self, user_id: int, day: date, *, tz_name: str) -> list[MealDTO]:
        """Return non-deleted meals whose local calendar day matches ``day`` in ``tz_name``."""

    async def get_meals_range(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> list[MealDTO]:
        """Return meals with ``eaten_at`` in ``[start, end)``, not deleted."""

    async def delete_meal(self, meal_id: int, user_id: int) -> bool:
        """Soft-delete a meal. Returns ``True`` if a row was updated."""

    async def get_user_settings(self, user_id: int) -> UserSettingsDTO | None:
        """Return merged view of profile + app settings (``None`` if user unknown)."""

    async def save_user_settings(self, user_id: int, settings: UserSettingsDTO) -> None:
        """Upsert settings for ``user_id``."""

    async def get_daily_aggregates(self, user_id: int, day: date) -> DailyAggregateDTO | None:
        """Return materialized daily rollup if present (else ``None``)."""

    async def get_range_aggregates(
        self,
        user_id: int,
        start_day: date,
        end_day: date,
    ) -> list[DailyAggregateDTO]:
        """Return ordered daily aggregates with ``start_day <= d < end_day`` (date half-open)."""
