from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import MealHistory


class MealHistoryRepository:
    """Persist meal audit history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_event(
        self,
        user_id: int,
        meal_id: int,
        event_type: str,
        snapshot: dict | None,
    ) -> MealHistory:
        """Add a meal history event."""
        event = MealHistory(
            user_id=user_id,
            meal_id=meal_id,
            event_type=event_type,
            snapshot=snapshot,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_meal(self, user_id: int, meal_id: int) -> list[MealHistory]:
        """Return audit events for a user-owned meal."""
        result = await self._session.execute(
            select(MealHistory)
            .where(MealHistory.user_id == user_id, MealHistory.meal_id == meal_id)
            .order_by(MealHistory.created_at)
        )
        return list(result.scalars())
