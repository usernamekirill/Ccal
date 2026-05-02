"""Smoke tests for compact Telegram meal preview strings."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.utils import ux_formatter


def _result() -> FoodRecognitionResult:
    return FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="кулич",
                portion_description="50 г",
                estimated_grams=50,
                calories=150,
                protein=None,
                fat=None,
                carbs=None,
                confidence=0.9,
            )
        ],
        total_calories=150,
        overall_confidence=0.9,
        comment="ок",
        meal_type="lunch",
    )


def test_format_meal_review_contains_grams_and_total() -> None:
    text = ux_formatter.format_meal_review(_result(), show_low_confidence_hint=False)
    assert "50" in text
    assert "кулич" in text.lower()
    assert "150" in text
    assert "Итого" in text


def test_format_saved_brief_single_item() -> None:
    text = ux_formatter.format_saved_brief(_result())
    assert "кулич" in text.lower()
    assert "Итого: ≈ 150" in text
