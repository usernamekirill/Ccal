from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource
from calorie_bot.app.keyboards.meal import photo_review_keyboard
from calorie_bot.app.services.meal_service import MealService


class FakeMealRepository:
    """Fake meal repository for saved meal edit tests."""

    def __init__(self) -> None:
        self.meal = SimpleNamespace(
            id=10,
            status="confirmed",
            source="photo",
            meal_type=None,
            eaten_at=datetime(2026, 4, 30, tzinfo=UTC),
            deleted_at=None,
            total_calories=300,
            total_protein_g=20,
            total_fat_g=10,
            total_carbs_g=30,
            ai_confidence=0.8,
            items=[
                SimpleNamespace(
                    name="рис",
                    portion_text="200 г",
                    grams=200,
                    calories=300,
                    protein_g=6,
                    fat_g=1,
                    carbs_g=65,
                    confidence=0.8,
                )
            ],
        )

    async def get_user_meal(self, user_id: int, meal_id: int):
        """Return a deterministic saved meal."""
        return self.meal if user_id == 1 and meal_id == self.meal.id else None

    async def replace_meal(self, meal, draft: MealDraft):
        """Apply draft totals to the fake meal."""
        meal.total_calories = draft.total_calories
        meal.items = [
            SimpleNamespace(
                name=item.name,
                portion_text=item.portion_text,
                grams=item.grams,
                calories=item.calories,
                protein_g=item.protein_g,
                fat_g=item.fat_g,
                carbs_g=item.carbs_g,
                confidence=item.confidence,
            )
            for item in draft.items
        ]
        return meal

    async def soft_delete(self, meal, deleted_at: datetime):
        """Mark the fake meal as deleted."""
        meal.deleted_at = deleted_at
        return meal


class FakeChangeLogRepository:
    """Fake change log repository for saved meal edit tests."""

    def __init__(self) -> None:
        self.logs = []

    async def add_log(self, **kwargs):
        """Store change log kwargs."""
        self.logs.append(kwargs)
        return SimpleNamespace(**kwargs)


@pytest.mark.asyncio
async def test_updates_saved_meal_and_writes_change_log() -> None:
    """Saved meal edits should persist and record before/after snapshots."""
    meal_repository = FakeMealRepository()
    change_logs = FakeChangeLogRepository()
    service = MealService(meal_repository, change_logs)
    draft = MealDraft(
        items=[MealItemDraft(name="рис", calories=180, grams=120)],
        total_calories=180,
        source=MealSource.MIXED,
    )

    updated = await service.update_saved_meal(user_id=1, meal_id=10, draft=draft)

    assert updated.total_calories == 180
    assert change_logs.logs[0]["action"] == "updated"
    assert change_logs.logs[0]["before_snapshot"]["total_calories"] == 300
    assert change_logs.logs[0]["after_snapshot"]["total_calories"] == 180


@pytest.mark.asyncio
async def test_deletes_saved_meal_and_writes_change_log() -> None:
    """Saved meal deletion should be soft and auditable."""
    meal_repository = FakeMealRepository()
    change_logs = FakeChangeLogRepository()
    service = MealService(meal_repository, change_logs)
    deleted_at = datetime(2026, 4, 30, 12, tzinfo=UTC)

    deleted = await service.delete_saved_meal(user_id=1, meal_id=10, deleted_at=deleted_at)

    assert deleted.deleted_at == deleted_at
    assert change_logs.logs[0]["action"] == "deleted"
    assert change_logs.logs[0]["after_snapshot"]["deleted_at"] == deleted_at.isoformat()


def test_photo_review_keyboard_contains_required_actions() -> None:
    """Review keyboard should expose save, cancel, one edit entry, voice, meal type."""
    labels = [
        button.text
        for row in photo_review_keyboard().inline_keyboard
        for button in row
    ]

    assert "✅ Сохранить" in labels
    assert "✏️ Изменить" in labels
    assert "➕ Добавить продукт" in labels
    assert "🗑 Удалить продукт" in labels
    assert "❌ Отмена" in labels
