from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from calorie_bot.app.database.models import Meal
from calorie_bot.app.domain import MealStatus


class StatsRepository:
    """Read-only queries for nutrition statistics windows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_confirmed_meals_between(
        self,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Meal]:
        """Return confirmed, non-deleted meals with items in ``[start_at, end_at)``."""
        result = await self._session.execute(
            self._meal_query().where(
                Meal.user_id == user_id,
                Meal.status == MealStatus.CONFIRMED.value,
                Meal.eaten_at >= start_at,
                Meal.eaten_at < end_at,
                Meal.deleted_at.is_(None),
            )
        )
        return list(result.scalars().unique())

    def _meal_query(self) -> Select[tuple[Meal]]:
        return select(Meal).options(selectinload(Meal.items))
