from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import MealItem


class MealItemRepository:
    """Load meal item records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_meal_id(self, meal_id: int) -> list[MealItem]:
        """Return all items for a meal."""
        result = await self._session.execute(select(MealItem).where(MealItem.meal_id == meal_id))
        return list(result.scalars())
