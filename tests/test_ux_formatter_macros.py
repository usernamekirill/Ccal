"""Preview card shows macro totals."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.utils import ux_formatter


def test_format_meal_review_includes_macro_totals() -> None:
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="а",
                portion_description="100 г",
                estimated_grams=100.0,
                calories=100,
                protein=10.0,
                fat=5.0,
                carbs=10.0,
                food_confidence=0.95,
                portion_confidence=0.9,
                grams_source="user",
                is_estimated=False,
                confidence=0.95,
            ),
            FoodItemRecognition(
                name="б",
                portion_description="100 г",
                estimated_grams=100.0,
                calories=100,
                protein=5.0,
                fat=5.0,
                carbs=5.0,
                food_confidence=0.95,
                portion_confidence=0.9,
                grams_source="user",
                is_estimated=False,
                confidence=0.95,
            ),
        ],
        total_calories=200,
        overall_confidence=0.95,
        comment="t",
    )
    r = svc.validate_food_result(r)
    text = ux_formatter.format_meal_review(r)
    assert "БЖУ всего" in text
    assert "Б 15" in text or "Б 15" in text.replace(",", ".")
    assert "Ж 10" in text
    assert "У 15" in text
