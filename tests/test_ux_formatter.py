"""Smoke tests for compact Telegram meal preview strings."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
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


def test_format_meal_review_skips_shallow_macro_total_mismatch_warning() -> None:
    """Small Atwater vs declared kcal spread should not spam the mismatch banner."""
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="тест",
                portion_description="100 г",
                estimated_grams=100.0,
                calories=100,
                protein=4.5,
                fat=4.5,
                carbs=9.0,
                food_confidence=0.9,
                portion_confidence=0.9,
                confidence=0.9,
            )
        ],
        total_calories=100,
        overall_confidence=0.9,
        comment="x",
    )
    r = svc.validate_food_result(r)
    text = ux_formatter.format_meal_review(r)
    assert "расходятся" not in text


def test_format_meal_review_hides_macro_total_mismatch_banner() -> None:
    """Macro vs calorie gap is not shown to users (backend still validates elsewhere)."""
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="тест",
                portion_description="100 г",
                estimated_grams=100.0,
                calories=200,
                protein=4.5,
                fat=4.5,
                carbs=9.0,
                food_confidence=0.9,
                portion_confidence=0.9,
                confidence=0.9,
            )
        ],
        total_calories=200,
        overall_confidence=0.9,
        comment="x",
    )
    text = ux_formatter.format_meal_review(r)
    assert "расходятся" not in text
    assert "БЖУ всего" in text
