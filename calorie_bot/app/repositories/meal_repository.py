from datetime import datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from calorie_bot.app.database.models import Meal, MealItem
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource, MealStatus


class MealRepository:
    """Persist meal drafts and confirmed meals."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_draft(self, user_id: int, meal: MealDraft, eaten_at: datetime) -> Meal:
        """Create a new meal draft from a structured meal draft."""
        total_protein, total_fat, total_carbs = _sum_macros(meal.items)
        db_meal = Meal(
            user_id=user_id,
            status=MealStatus.DRAFT.value,
            source=meal.source.value,
            meal_type=meal.meal_type.value if meal.meal_type else None,
            eaten_at=eaten_at,
            total_calories=meal.total_calories,
            total_calories_min=meal.total_calories_min,
            total_calories_max=meal.total_calories_max,
            has_estimated_items=meal.has_estimated_items,
            total_protein_g=total_protein,
            total_fat_g=total_fat,
            total_carbs_g=total_carbs,
            ai_confidence=meal.confidence,
        )
        self._session.add(db_meal)
        await self._session.flush()
        await self.replace_items(db_meal.id, meal.items)
        return db_meal

    async def get_user_meal(self, user_id: int, meal_id: int) -> Meal | None:
        """Return a meal if it belongs to the given user."""
        result = await self._session.execute(
            self._meal_query().where(
                Meal.user_id == user_id,
                Meal.id == meal_id,
                Meal.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_draft(self, user_id: int) -> Meal | None:
        """Return the latest draft meal for a user."""
        result = await self._session.execute(
            self._meal_query()
            .where(
                Meal.user_id == user_id,
                Meal.status == MealStatus.DRAFT.value,
                Meal.deleted_at.is_(None),
            )
            .order_by(Meal.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def transition_latest_draft_status(
        self,
        user_id: int,
        *,
        from_status: str,
        to_status: str,
    ) -> Meal | None:
        """Atomically move the user's newest draft from ``from_status`` to ``to_status``.

        Uses a single ``UPDATE … WHERE id = (SELECT … LIMIT 1) AND status = draft``
        so concurrent double-clicks only apply once; the losing transaction updates
        zero rows and returns ``None``.
        """
        latest_id_subq = (
            select(Meal.id)
            .where(
                Meal.user_id == user_id,
                Meal.status == from_status,
                Meal.deleted_at.is_(None),
            )
            .order_by(Meal.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            update(Meal)
            .where(
                Meal.id == latest_id_subq,
                Meal.user_id == user_id,
                Meal.status == from_status,
            )
            .values(status=to_status)
            .returning(Meal.id)
        )
        result = await self._session.execute(stmt)
        meal_id = result.scalar_one_or_none()
        if meal_id is None:
            return None
        return await self.get_user_meal(user_id, int(meal_id))

    async def replace_draft(self, meal: Meal, draft: MealDraft) -> Meal:
        """Replace draft meal totals and items."""
        total_protein, total_fat, total_carbs = _sum_macros(draft.items)
        meal.total_calories = draft.total_calories
        meal.total_calories_min = draft.total_calories_min
        meal.total_calories_max = draft.total_calories_max
        meal.has_estimated_items = draft.has_estimated_items
        meal.total_protein_g = total_protein
        meal.total_fat_g = total_fat
        meal.total_carbs_g = total_carbs
        meal.ai_confidence = draft.confidence
        meal.source = MealSource.MIXED.value if meal.source != draft.source.value else meal.source
        meal.meal_type = draft.meal_type.value if draft.meal_type else meal.meal_type
        await self.replace_items(meal.id, draft.items)
        return meal

    async def confirm(self, meal: Meal) -> Meal:
        """Mark a draft meal as confirmed."""
        meal.status = MealStatus.CONFIRMED.value
        return meal

    async def cancel(self, meal: Meal) -> Meal:
        """Mark a draft meal as cancelled."""
        meal.status = MealStatus.CANCELLED.value
        return meal

    async def replace_meal(self, meal: Meal, draft: MealDraft) -> Meal:
        """Replace a meal's totals and items after a user edit."""
        total_protein, total_fat, total_carbs = _sum_macros(draft.items)
        meal.total_calories = draft.total_calories
        meal.total_calories_min = draft.total_calories_min
        meal.total_calories_max = draft.total_calories_max
        meal.has_estimated_items = draft.has_estimated_items
        meal.total_protein_g = total_protein
        meal.total_fat_g = total_fat
        meal.total_carbs_g = total_carbs
        meal.ai_confidence = draft.confidence
        meal.source = MealSource.MIXED.value if meal.source != draft.source.value else meal.source
        meal.meal_type = draft.meal_type.value if draft.meal_type else meal.meal_type
        await self.replace_items(meal.id, draft.items)
        return meal

    async def soft_delete(self, meal: Meal, deleted_at: datetime) -> Meal:
        """Soft-delete a meal owned by a user."""
        meal.deleted_at = deleted_at
        return meal

    async def replace_items(self, meal_id: int, items: list[MealItemDraft]) -> None:
        """Replace all items for a meal."""
        existing_result = await self._session.execute(
            select(MealItem).where(MealItem.meal_id == meal_id)
        )
        for item in existing_result.scalars():
            await self._session.delete(item)

        for item in items:
            gs = item.grams_source.value if item.grams_source else None
            self._session.add(
                MealItem(
                    meal_id=meal_id,
                    name=item.name,
                    portion_text=item.portion_text,
                    grams=item.grams,
                    grams_min=item.grams_min,
                    grams_max=item.grams_max,
                    grams_source=gs,
                    calories=item.calories,
                    calories_min=item.calories_min,
                    calories_max=item.calories_max,
                    calories_per_100g=item.calories_per_100g,
                    protein_per_100g=item.protein_per_100g,
                    fat_per_100g=item.fat_per_100g,
                    carbs_per_100g=item.carbs_per_100g,
                    protein_g=item.protein_g,
                    fat_g=item.fat_g,
                    carbs_g=item.carbs_g,
                    protein_g_min=item.protein_g_min,
                    protein_g_max=item.protein_g_max,
                    fat_g_min=item.fat_g_min,
                    fat_g_max=item.fat_g_max,
                    carbs_g_min=item.carbs_g_min,
                    carbs_g_max=item.carbs_g_max,
                    food_confidence=item.food_confidence,
                    portion_confidence=item.portion_confidence,
                    needs_portion_clarification=item.needs_portion_clarification,
                    is_estimated=item.is_estimated,
                    confidence=item.confidence,
                )
            )
        await self._session.flush()

    async def list_confirmed_between(
        self,
        user_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Meal]:
        """Return confirmed meals for a period."""
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

    async def latest_confirmed_eaten_at(self, user_id: int) -> datetime | None:
        """Return eaten_at of the most recent confirmed meal, if any."""
        result = await self._session.execute(
            select(Meal.eaten_at)
            .where(
                Meal.user_id == user_id,
                Meal.status == MealStatus.CONFIRMED.value,
                Meal.deleted_at.is_(None),
            )
            .order_by(Meal.eaten_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_confirmed_meals(self, user_id: int) -> int:
        """Count all-time confirmed meals (not deleted)."""
        result = await self._session.execute(
            select(func.count())
            .select_from(Meal)
            .where(
                Meal.user_id == user_id,
                Meal.status == MealStatus.CONFIRMED.value,
                Meal.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    def _meal_query(self) -> Select[tuple[Meal]]:
        return select(Meal).options(selectinload(Meal.items))


def _sum_macros(items: list[MealItemDraft]) -> tuple[float, float, float]:
    protein = sum(item.protein_g or 0 for item in items)
    fat = sum(item.fat_g or 0 for item in items)
    carbs = sum(item.carbs_g or 0 for item in items)
    return protein, fat, carbs
