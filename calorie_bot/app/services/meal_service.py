from datetime import datetime

from calorie_bot.app.database.models import Meal
from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource, MealType
from calorie_bot.app.repositories.meal_change_log_repository import MealChangeLogRepository
from calorie_bot.app.repositories.meal_repository import MealRepository


class MealService:
    """Coordinate meal draft, confirmation, and cancellation operations."""

    def __init__(
        self,
        meal_repository: MealRepository,
        change_log_repository: MealChangeLogRepository | None = None,
    ) -> None:
        self._meal_repository = meal_repository
        self._change_log_repository = change_log_repository

    async def create_draft(self, user_id: int, meal: MealDraft, eaten_at: datetime) -> Meal:
        """Create a meal draft that requires user confirmation."""
        return await self._meal_repository.create_draft(user_id, meal, eaten_at)

    async def latest_draft(self, user_id: int) -> Meal | None:
        """Return latest draft meal for a user."""
        return await self._meal_repository.get_latest_draft(user_id)

    async def apply_draft_update(self, meal: Meal, draft: MealDraft) -> Meal:
        """Apply updated draft values after a correction."""
        return await self._meal_repository.replace_draft(meal, draft)

    async def confirm_latest_draft(self, user_id: int) -> Meal | None:
        """Confirm the latest draft meal for a user."""
        meal = await self._meal_repository.get_latest_draft(user_id)
        if meal is None:
            return None
        return await self._meal_repository.confirm(meal)

    async def cancel_latest_draft(self, user_id: int) -> Meal | None:
        """Cancel the latest draft meal for a user."""
        meal = await self._meal_repository.get_latest_draft(user_id)
        if meal is None:
            return None
        return await self._meal_repository.cancel(meal)

    async def update_saved_meal(
        self,
        user_id: int,
        meal_id: int,
        draft: MealDraft,
    ) -> Meal | None:
        """Update a confirmed meal and write a before/after change log."""
        meal = await self._meal_repository.get_user_meal(user_id, meal_id)
        if meal is None:
            return None
        before = meal_model_to_snapshot(meal)
        updated = await self._meal_repository.replace_meal(meal, draft)
        if self._change_log_repository is not None:
            await self._change_log_repository.add_log(
                user_id=user_id,
                meal_id=updated.id,
                action="updated",
                before_snapshot=before,
                after_snapshot=meal_draft_to_snapshot(updated, draft),
            )
        return updated

    async def delete_saved_meal(
        self,
        user_id: int,
        meal_id: int,
        deleted_at: datetime,
    ) -> Meal | None:
        """Soft-delete a saved meal and write a change log."""
        meal = await self._meal_repository.get_user_meal(user_id, meal_id)
        if meal is None:
            return None
        before = meal_model_to_snapshot(meal)
        deleted = await self._meal_repository.soft_delete(meal, deleted_at)
        if self._change_log_repository is not None:
            await self._change_log_repository.add_log(
                user_id=user_id,
                meal_id=deleted.id,
                action="deleted",
                before_snapshot=before,
                after_snapshot=meal_model_to_snapshot(deleted),
            )
        return deleted


def meal_model_to_draft(meal: Meal) -> MealDraft:
    """Convert a database meal model to an in-memory draft."""
    items = [
        MealItemDraft(
            name=item.name,
            portion_text=item.portion_text,
            grams=item.grams,
            calories=item.calories,
            protein_g=item.protein_g,
            fat_g=item.fat_g,
            carbs_g=item.carbs_g,
            confidence=item.confidence,
        )
        for item in meal.items
    ]
    return MealDraft(
        items=items,
        total_calories=sum(item.calories for item in items),
        source=MealSource(meal.source),
        meal_type=MealType(meal.meal_type) if meal.meal_type else None,
        confidence=meal.ai_confidence,
    )


def meal_model_to_snapshot(meal: Meal) -> dict:
    """Convert a meal model to a JSON-safe audit snapshot."""
    return {
        "id": meal.id,
        "status": meal.status,
        "source": meal.source,
        "meal_type": meal.meal_type,
        "eaten_at": meal.eaten_at.isoformat(),
        "deleted_at": meal.deleted_at.isoformat() if meal.deleted_at else None,
        "total_calories": meal.total_calories,
        "total_protein_g": meal.total_protein_g,
        "total_fat_g": meal.total_fat_g,
        "total_carbs_g": meal.total_carbs_g,
        "ai_confidence": meal.ai_confidence,
        "items": [
            {
                "name": item.name,
                "portion_text": item.portion_text,
                "grams": item.grams,
                "calories": item.calories,
                "protein_g": item.protein_g,
                "fat_g": item.fat_g,
                "carbs_g": item.carbs_g,
                "confidence": item.confidence,
            }
            for item in meal.items
        ],
    }


def meal_draft_to_snapshot(meal: Meal, draft: MealDraft) -> dict:
    """Convert updated meal metadata and draft values to an audit snapshot."""
    return {
        "id": meal.id,
        "status": meal.status,
        "source": meal.source,
        "meal_type": meal.meal_type,
        "eaten_at": meal.eaten_at.isoformat(),
        "deleted_at": meal.deleted_at.isoformat() if meal.deleted_at else None,
        "total_calories": draft.total_calories,
        "total_protein_g": sum(item.protein_g or 0 for item in draft.items),
        "total_fat_g": sum(item.fat_g or 0 for item in draft.items),
        "total_carbs_g": sum(item.carbs_g or 0 for item in draft.items),
        "ai_confidence": draft.confidence,
        "items": [
            {
                "name": item.name,
                "portion_text": item.portion_text,
                "grams": item.grams,
                "calories": item.calories,
                "protein_g": item.protein_g,
                "fat_g": item.fat_g,
                "carbs_g": item.carbs_g,
                "confidence": item.confidence,
            }
            for item in draft.items
        ],
    }
