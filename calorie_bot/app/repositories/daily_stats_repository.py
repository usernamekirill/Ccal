from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.database.models import DailyStats, UserProfile


class DailyStatsRepository:
    """Persist and read denormalized daily nutrition statistics."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_date(self, user_id: int, stat_date: datetime) -> DailyStats | None:
        """Return daily stats for a user and date."""
        result = await self._session.execute(
            select(DailyStats).where(
                DailyStats.user_id == user_id,
                DailyStats.stat_date == stat_date,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_for_date(
        self,
        user_id: int,
        stat_date: datetime,
        total_calories: int,
        total_protein_g: float,
        total_fat_g: float,
        total_carbs_g: float,
        meals_count: int,
        calorie_target: int | None,
    ) -> DailyStats:
        """Create or update daily stats for a user and date."""
        stats = await self.get_for_date(user_id, stat_date)
        if stats is None:
            stats = DailyStats(user_id=user_id, stat_date=stat_date)
            self._session.add(stats)

        stats.total_calories = total_calories
        stats.total_protein_g = total_protein_g
        stats.total_fat_g = total_fat_g
        stats.total_carbs_g = total_carbs_g
        stats.meals_count = meals_count
        stats.calorie_target = calorie_target
        return stats

    async def list_between(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> list[DailyStats]:
        """Return daily stats for trend calculations."""
        result = await self._session.execute(
            select(DailyStats)
            .where(
                DailyStats.user_id == user_id,
                DailyStats.stat_date >= start_date,
                DailyStats.stat_date < end_date,
            )
            .order_by(DailyStats.stat_date)
        )
        return list(result.scalars())

    async def sync_targets_from_profile(self, user_id: int, profile: UserProfile) -> None:
        """Align denormalized daily targets with the current profile for progress metrics."""
        await self._session.execute(
            update(DailyStats)
            .where(DailyStats.user_id == user_id)
            .values(
                calorie_target=profile.daily_calorie_target,
                protein_target_g=profile.daily_protein_target_g,
                fat_target_g=profile.daily_fat_target_g,
                carbs_target_g=profile.daily_carbs_target_g,
            ),
        )

    async def add_confirmed_meal_totals(
        self,
        user_id: int,
        stat_anchor: datetime,
        *,
        calories: int,
        protein_g: float,
        fat_g: float,
        carbs_g: float,
        profile: UserProfile | None,
    ) -> None:
        """Increment rollups when a meal is confirmed."""
        stats = await self.get_for_date(user_id, stat_anchor)
        if stats is None:
            stats = DailyStats(
                user_id=user_id,
                stat_date=stat_anchor,
                total_calories=calories,
                total_protein_g=protein_g,
                total_fat_g=fat_g,
                total_carbs_g=carbs_g,
                meals_count=1,
                calorie_target=profile.daily_calorie_target if profile else None,
                protein_target_g=profile.daily_protein_target_g if profile else None,
                fat_target_g=profile.daily_fat_target_g if profile else None,
                carbs_target_g=profile.daily_carbs_target_g if profile else None,
            )
            self._session.add(stats)
            return

        stats.total_calories += calories
        stats.total_protein_g += protein_g
        stats.total_fat_g += fat_g
        stats.total_carbs_g += carbs_g
        stats.meals_count += 1

    async def subtract_confirmed_meal_totals(
        self,
        user_id: int,
        stat_anchor: datetime,
        *,
        calories: int,
        protein_g: float,
        fat_g: float,
        carbs_g: float,
    ) -> None:
        """Reverse rollups when a confirmed meal is soft-deleted."""
        stats = await self.get_for_date(user_id, stat_anchor)
        if stats is None:
            return
        stats.total_calories = max(0, stats.total_calories - calories)
        stats.total_protein_g = max(0.0, float(stats.total_protein_g) - protein_g)
        stats.total_fat_g = max(0.0, float(stats.total_fat_g) - fat_g)
        stats.total_carbs_g = max(0.0, float(stats.total_carbs_g) - carbs_g)
        stats.meals_count = max(0, stats.meals_count - 1)
