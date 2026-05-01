from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import MealChangeLog


class MealChangeLogRepository:
    """Persist before/after snapshots for meal changes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_log(
        self,
        user_id: int,
        meal_id: int,
        action: str,
        before_snapshot: dict | None,
        after_snapshot: dict | None,
    ) -> MealChangeLog:
        """Create a meal change log entry."""
        log = MealChangeLog(
            user_id=user_id,
            meal_id=meal_id,
            action=action,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        self._session.add(log)
        await self._session.flush()
        return log

    async def list_for_meal(self, user_id: int, meal_id: int) -> list[MealChangeLog]:
        """Return change logs for a user-owned meal."""
        result = await self._session.execute(
            select(MealChangeLog)
            .where(MealChangeLog.user_id == user_id, MealChangeLog.meal_id == meal_id)
            .order_by(MealChangeLog.created_at)
        )
        return list(result.scalars())
