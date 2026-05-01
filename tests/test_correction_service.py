from calorie_bot.app.domain import MealDraft, MealItemDraft, MealSource
from calorie_bot.app.services.correction_service import CorrectionService


def test_creates_text_meal_draft_from_simple_calorie_input() -> None:
    """Text input should create a confirmable meal draft without AI."""
    draft = CorrectionService().apply_text(None, "кофе с молоком 80 ккал")

    assert draft.source == MealSource.TEXT
    assert draft.total_calories == 80
    assert draft.items[0].name == "кофе с молоком"


def test_add_command_appends_item_to_existing_draft() -> None:
    """Add command should reuse draft context and avoid a repeated vision call."""
    current = MealDraft(
        items=[MealItemDraft(name="рис", calories=200)],
        total_calories=200,
        source=MealSource.PHOTO,
    )

    updated = CorrectionService().apply_text(current, "добавь кофе 80 ккал")

    assert updated.source == MealSource.MIXED
    assert updated.total_calories == 280
    assert [item.name for item in updated.items] == ["рис", "кофе"]
