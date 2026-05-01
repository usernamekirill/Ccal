from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import MealAIResult


class MealAIResultRepository:
    """Persist structured AI recognition results without raw media."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_result(
        self,
        user_id: int,
        request_type: str,
        meal_id: int | None = None,
        model: str | None = None,
        confidence: float | None = None,
        structured_result: dict | None = None,
        status: str = "succeeded",
    ) -> MealAIResult:
        """Create an AI result record scoped to a user."""
        result = MealAIResult(
            user_id=user_id,
            meal_id=meal_id,
            request_type=request_type,
            model=model,
            confidence=confidence,
            structured_result=structured_result,
            status=status,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def get_latest_for_meal(self, user_id: int, meal_id: int) -> MealAIResult | None:
        """Return the latest AI result for a user's meal."""
        result = await self._session.execute(
            select(MealAIResult)
            .where(MealAIResult.user_id == user_id, MealAIResult.meal_id == meal_id)
            .order_by(MealAIResult.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
