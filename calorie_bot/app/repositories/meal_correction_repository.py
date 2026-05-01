from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import MealCorrection


class MealCorrectionRepository:
    """Persist user corrections and before/after snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_correction(
        self,
        user_id: int,
        meal_id: int,
        source: str,
        correction_text: str | None,
        before_snapshot: dict | None,
        after_snapshot: dict | None,
    ) -> MealCorrection:
        """Add a correction record for a user-owned meal."""
        correction = MealCorrection(
            user_id=user_id,
            meal_id=meal_id,
            source=source,
            correction_text=correction_text,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
        )
        self._session.add(correction)
        await self._session.flush()
        return correction

    async def list_for_meal(self, user_id: int, meal_id: int) -> list[MealCorrection]:
        """Return corrections for a user-owned meal."""
        result = await self._session.execute(
            select(MealCorrection)
            .where(MealCorrection.user_id == user_id, MealCorrection.meal_id == meal_id)
            .order_by(MealCorrection.created_at)
        )
        return list(result.scalars())
