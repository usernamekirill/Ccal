"""Hard-delete all user-owned rows for GDPR-style data removal."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import (
    AIRequest,
    DailyStats,
    ErrorLog,
    Meal,
    MealAIResult,
    MealChangeLog,
    MealCorrection,
    MealHistory,
    MealItem,
    MotivationEvent,
    User,
    UserProfile,
    UserSettings,
    WeightLog,
)


class UserPurgeRepository:
    """Remove every persisted record tied to an internal user id."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge_user_data(self, user_id: int) -> None:
        """Delete meals and related rows, then settings, profile, and the user.

        The Telegram account can register again as a new internal user on next /start.
        """
        meal_ids = list(
            (await self._session.scalars(select(Meal.id).where(Meal.user_id == user_id))).all()
        )
        if meal_ids:
            await self._session.execute(delete(MealItem).where(MealItem.meal_id.in_(meal_ids)))
            await self._session.execute(
                delete(MealCorrection).where(MealCorrection.meal_id.in_(meal_ids)),
            )
            await self._session.execute(
                delete(MealHistory).where(MealHistory.meal_id.in_(meal_ids)),
            )
            await self._session.execute(
                delete(MealChangeLog).where(MealChangeLog.meal_id.in_(meal_ids)),
            )

        await self._session.execute(delete(MealAIResult).where(MealAIResult.user_id == user_id))
        await self._session.execute(delete(AIRequest).where(AIRequest.user_id == user_id))
        await self._session.execute(delete(Meal).where(Meal.user_id == user_id))
        await self._session.execute(delete(WeightLog).where(WeightLog.user_id == user_id))
        await self._session.execute(delete(DailyStats).where(DailyStats.user_id == user_id))
        await self._session.execute(
            delete(MotivationEvent).where(MotivationEvent.user_id == user_id),
        )
        await self._session.execute(delete(ErrorLog).where(ErrorLog.user_id == user_id))
        await self._session.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
        await self._session.execute(delete(UserSettings).where(UserSettings.user_id == user_id))
        await self._session.execute(delete(User).where(User.id == user_id))
        await self._session.flush()
