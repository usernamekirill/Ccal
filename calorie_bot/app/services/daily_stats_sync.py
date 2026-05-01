"""Keep denormalized ``daily_stats`` in sync with confirmed meals (cheap reads)."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from calorie_bot.app.config import Settings
from calorie_bot.app.database.models import Meal
from calorie_bot.app.domain import MealStatus
from calorie_bot.app.repositories.daily_stats_repository import DailyStatsRepository
from calorie_bot.app.repositories.profile_repository import ProfileRepository
from calorie_bot.app.utils.stat_anchor import stat_anchor_from_eaten_at


async def on_meal_confirmed(
    session: AsyncSession,
    settings: Settings,
    *,
    user_sql_id: int,
    meal: Meal,
) -> None:
    """Call after a meal transitions to confirmed and is flushed."""
    profile = await ProfileRepository(session).get_by_user_id(user_sql_id)
    tz = profile.timezone if profile and profile.timezone else settings.timezone
    anchor = stat_anchor_from_eaten_at(meal.eaten_at, tz)
    await DailyStatsRepository(session).add_confirmed_meal_totals(
        user_sql_id,
        anchor,
        calories=meal.total_calories,
        protein_g=float(meal.total_protein_g or 0),
        fat_g=float(meal.total_fat_g or 0),
        carbs_g=float(meal.total_carbs_g or 0),
        profile=profile,
    )


async def on_confirmed_meal_edited(
    session: AsyncSession,
    settings: Settings,
    *,
    user_sql_id: int,
    before_eaten_at: datetime,
    before_calories: int,
    before_protein_g: float,
    before_fat_g: float,
    before_carbs_g: float,
    before_status: str,
    after_meal: Meal,
) -> None:
    """Adjust rollups after an in-place edit of totals/items on a saved meal.

    Uses subtract + add so ``meals_count`` stays correct (net zero when the meal
    stays on the same ``stat_date``). If ``eaten_at`` ever splits across local
    days, each day's row is updated accordingly.
    """
    if before_status != MealStatus.CONFIRMED.value:
        return
    if after_meal.status != MealStatus.CONFIRMED.value:
        return
    profile = await ProfileRepository(session).get_by_user_id(user_sql_id)
    tz = profile.timezone if profile and profile.timezone else settings.timezone
    old_anchor = stat_anchor_from_eaten_at(before_eaten_at, tz)
    new_anchor = stat_anchor_from_eaten_at(after_meal.eaten_at, tz)
    repo = DailyStatsRepository(session)
    await repo.subtract_confirmed_meal_totals(
        user_sql_id,
        old_anchor,
        calories=before_calories,
        protein_g=before_protein_g,
        fat_g=before_fat_g,
        carbs_g=before_carbs_g,
    )
    await repo.add_confirmed_meal_totals(
        user_sql_id,
        new_anchor,
        calories=after_meal.total_calories,
        protein_g=float(after_meal.total_protein_g or 0),
        fat_g=float(after_meal.total_fat_g or 0),
        carbs_g=float(after_meal.total_carbs_g or 0),
        profile=profile,
    )


async def on_meal_soft_deleted(
    session: AsyncSession,
    settings: Settings,
    *,
    user_sql_id: int,
    meal: Meal,
) -> None:
    """Call after a confirmed meal is soft-deleted (row still has eaten_at / totals)."""
    profile = await ProfileRepository(session).get_by_user_id(user_sql_id)
    tz = profile.timezone if profile and profile.timezone else settings.timezone
    anchor = stat_anchor_from_eaten_at(meal.eaten_at, tz)
    await DailyStatsRepository(session).subtract_confirmed_meal_totals(
        user_sql_id,
        anchor,
        calories=meal.total_calories,
        protein_g=float(meal.total_protein_g or 0),
        fat_g=float(meal.total_fat_g or 0),
        carbs_g=float(meal.total_carbs_g or 0),
    )
