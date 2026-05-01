"""SQLAlchemy implementation of ``StorageInterface`` (SQLite and Postgres compatible)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from calorie_bot.app.database.models import DailyStats, Meal, MealItem, UserProfile, UserSettings
from calorie_bot.app.domain import MealStatus
from calorie_bot.app.storage.dto import DailyAggregateDTO, MealDTO, MealItemDTO, UserSettingsDTO
from calorie_bot.app.storage.interface import StorageInterface


class SqlAlchemyStorage(StorageInterface):
    """Concrete storage using one ``AsyncSession`` per unit-of-work (handler request)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_meal(self, meal: MealDTO) -> MealDTO:
        """Persist meal and nested items."""
        if meal.id is None:
            return await self._insert_meal(meal)
        return await self._update_meal(meal)

    async def save_meals_batch(self, meals: list[MealDTO]) -> list[MealDTO]:
        """Persist several meals; flushes once at the end."""
        out: list[MealDTO] = []
        for m in meals:
            out.append(await self.save_meal(m))
        await self._session.flush()
        return out

    async def get_meals_by_day(self, user_id: int, day: date, *, tz_name: str) -> list[MealDTO]:
        """Filter by user's local calendar day."""
        tz = ZoneInfo(tz_name)
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = start + timedelta(days=1)
        return await self.get_meals_range(user_id, start, end)

    async def get_meals_range(
        self,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> list[MealDTO]:
        """Return confirmed, non-deleted meals in range with items loaded."""
        result = await self._session.execute(
            select(Meal)
            .options(selectinload(Meal.items))
            .where(
                Meal.user_id == user_id,
                Meal.status == MealStatus.CONFIRMED.value,
                Meal.eaten_at >= start,
                Meal.eaten_at < end,
                Meal.deleted_at.is_(None),
            )
            .order_by(Meal.eaten_at)
        )
        return [_meal_to_dto(m) for m in result.scalars().unique()]

    async def delete_meal(self, meal_id: int, user_id: int) -> bool:
        """Soft-delete."""
        meal = await self._session.get(Meal, meal_id)
        if meal is None or meal.user_id != user_id or meal.deleted_at is not None:
            return False
        meal.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return True

    async def get_user_settings(self, user_id: int) -> UserSettingsDTO | None:
        """Merge profile calorie target with ``user_settings`` row."""
        profile_result = await self._session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = profile_result.scalar_one_or_none()
        settings_row = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        s = settings_row.scalar_one_or_none()
        if profile is None and s is None:
            return None
        tz = s.timezone if s else (profile.timezone if profile else "Europe/Moscow")
        return UserSettingsDTO(
            user_id=user_id,
            timezone=tz,
            calorie_goal=profile.daily_calorie_target if profile else None,
            language=s.language if s else "ru",
            notifications_enabled=s.notifications_enabled if s else True,
            motivation_enabled=s.motivation_messages_enabled if s else True,
            ai_analysis_enabled=s.ai_analysis_enabled if s else True,
            measurement_unit=s.measurement_unit if s else "metric",
        )

    async def save_user_settings(self, user_id: int, settings: UserSettingsDTO) -> None:
        """Upsert ``UserSettings`` and calorie goal on profile when provided."""
        row_result = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        row = row_result.scalar_one_or_none()
        if row is None:
            row = UserSettings(user_id=user_id)
            self._session.add(row)
        row.timezone = settings.timezone
        row.language = settings.language
        row.notifications_enabled = settings.notifications_enabled
        row.motivation_messages_enabled = settings.motivation_enabled
        row.ai_analysis_enabled = settings.ai_analysis_enabled
        row.measurement_unit = settings.measurement_unit

        prof_result = await self._session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = prof_result.scalar_one_or_none()
        if profile is not None and settings.calorie_goal is not None:
            profile.daily_calorie_target = settings.calorie_goal
        await self._session.flush()

    async def get_daily_aggregates(self, user_id: int, day: date) -> DailyAggregateDTO | None:
        """Read ``daily_stats`` row anchored at local midnight (same convention as sync)."""
        anchor = await self._day_anchor(user_id, day)
        result = await self._session.execute(
            select(DailyStats).where(
                DailyStats.user_id == user_id,
                DailyStats.stat_date == anchor,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _daily_stats_to_dto(row, day)

    async def get_range_aggregates(
        self,
        user_id: int,
        start_day: date,
        end_day: date,
    ) -> list[DailyAggregateDTO]:
        """Half-open local calendar range ``[start_day, end_day)`` using anchored stat_date."""
        start_anchor = await self._day_anchor(user_id, start_day)
        end_anchor = await self._day_anchor(user_id, end_day)
        result = await self._session.execute(
            select(DailyStats)
            .where(
                DailyStats.user_id == user_id,
                DailyStats.stat_date >= start_anchor,
                DailyStats.stat_date < end_anchor,
            )
            .order_by(DailyStats.stat_date)
        )
        tz_name = (await self.get_user_settings(user_id))
        tz = ZoneInfo(tz_name.timezone if tz_name else "Europe/Moscow")
        out: list[DailyAggregateDTO] = []
        for row in result.scalars():
            local = row.stat_date.astimezone(tz)
            out.append(_daily_stats_to_dto(row, local.date()))
        return out

    async def _day_anchor(self, user_id: int, day: date) -> datetime:
        """Return timezone-aware midnight for ``day`` in the user's primary timezone."""
        snap = await self.get_user_settings(user_id)
        tz = ZoneInfo(snap.timezone if snap else "Europe/Moscow")
        return datetime.combine(day, time.min, tzinfo=tz)

    async def _insert_meal(self, meal: MealDTO) -> MealDTO:
        """Insert new meal graph."""
        db_meal = Meal(
            user_id=meal.user_id,
            status=meal.status,
            source=meal.source,
            meal_type=meal.meal_type,
            eaten_at=meal.eaten_at,
            total_calories=meal.calories,
            total_protein_g=meal.protein_g,
            total_fat_g=meal.fat_g,
            total_carbs_g=meal.carbs_g,
            ai_confidence=meal.ai_confidence,
        )
        self._session.add(db_meal)
        await self._session.flush()
        for item in meal.items:
            self._session.add(
                MealItem(
                    meal_id=db_meal.id,
                    name=item.name,
                    portion_text=item.portion_text,
                    grams=item.grams,
                    calories=item.calories,
                    protein_g=item.protein_g,
                    fat_g=item.fat_g,
                    carbs_g=item.carbs_g,
                )
            )
        await self._session.flush()
        await self._session.refresh(db_meal, attribute_names=["items"])
        return _meal_to_dto(db_meal)

    async def _update_meal(self, meal: MealDTO) -> MealDTO:
        """Replace totals and items for an existing meal."""
        result = await self._session.execute(
            select(Meal).options(selectinload(Meal.items)).where(Meal.id == meal.id)
        )
        db_meal = result.scalar_one_or_none()
        if db_meal is None or db_meal.user_id != meal.user_id:
            raise ValueError("meal not found for user")
        db_meal.status = meal.status
        db_meal.source = meal.source
        db_meal.meal_type = meal.meal_type
        db_meal.eaten_at = meal.eaten_at
        db_meal.total_calories = meal.calories
        db_meal.total_protein_g = meal.protein_g
        db_meal.total_fat_g = meal.fat_g
        db_meal.total_carbs_g = meal.carbs_g
        db_meal.ai_confidence = meal.ai_confidence
        await self._session.execute(delete(MealItem).where(MealItem.meal_id == db_meal.id))
        for item in meal.items:
            self._session.add(
                MealItem(
                    meal_id=db_meal.id,
                    name=item.name,
                    portion_text=item.portion_text,
                    grams=item.grams,
                    calories=item.calories,
                    protein_g=item.protein_g,
                    fat_g=item.fat_g,
                    carbs_g=item.carbs_g,
                )
            )
        await self._session.flush()
        await self._session.refresh(db_meal, attribute_names=["items"])
        return _meal_to_dto(db_meal)


def _meal_to_dto(m: Meal) -> MealDTO:
    """Map ORM meal to DTO."""
    items = [
        MealItemDTO(
            name=i.name,
            grams=i.grams,
            calories=i.calories,
            portion_text=i.portion_text,
            protein_g=i.protein_g,
            fat_g=i.fat_g,
            carbs_g=i.carbs_g,
        )
        for i in m.items
    ]
    return MealDTO(
        id=m.id,
        user_id=m.user_id,
        eaten_at=m.eaten_at,
        calories=m.total_calories,
        source=m.source,
        meal_type=m.meal_type,
        status=m.status,
        protein_g=float(m.total_protein_g or 0),
        fat_g=float(m.total_fat_g or 0),
        carbs_g=float(m.total_carbs_g or 0),
        ai_confidence=m.ai_confidence,
        is_deleted=m.deleted_at is not None,
        items=items,
    )


def _daily_stats_to_dto(row: DailyStats, day: date) -> DailyAggregateDTO:
    """Map ``DailyStats`` row to aggregate DTO."""
    return DailyAggregateDTO(
        user_id=row.user_id,
        day=day,
        total_calories=row.total_calories,
        meals_count=row.meals_count,
        calorie_goal=row.calorie_target,
        total_protein_g=float(row.total_protein_g or 0),
        total_fat_g=float(row.total_fat_g or 0),
        total_carbs_g=float(row.total_carbs_g or 0),
    )
