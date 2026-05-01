from datetime import datetime

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.domain import MealType
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.utils.meal_type import infer_meal_type


def test_text_food_schema_supports_meal_type_and_clarification() -> None:
    """Text food parser result should support meal type and one clarification question."""
    result = FoodRecognitionResult.model_validate(
        {
            "items": [
                {
                    "name": "кофе с молоком",
                    "portion_description": "1 стакан",
                    "estimated_grams": 250,
                    "calories": 120,
                    "protein": 5,
                    "fat": 4,
                    "carbs": 12,
                    "confidence": 0.8,
                }
            ],
            "total_calories": 120,
            "overall_confidence": 0.8,
            "comment": "Это приблизительная оценка.",
            "meal_type": "snack",
            "needs_clarification": False,
            "clarification_question": None,
        }
    )

    assert result.meal_type == "snack"
    assert result.needs_clarification is False


def test_calorie_service_sets_default_meal_type() -> None:
    """Calorie service should fill missing meal type from local time inference."""
    result = FoodRecognitionResult.model_validate(
        {
            "items": [
                {
                    "name": "гречка",
                    "portion_description": "200 г",
                    "estimated_grams": 200,
                    "calories": 220,
                    "protein": None,
                    "fat": None,
                    "carbs": None,
                    "confidence": 0.7,
                }
            ],
            "total_calories": 220,
            "overall_confidence": 0.7,
            "comment": "Это приблизительная оценка.",
        }
    )

    updated = CalorieService().with_default_meal_type(result, MealType.LUNCH)

    assert updated.meal_type == MealType.LUNCH.value


def test_infers_meal_type_from_time() -> None:
    """Meal type inference should use local hour buckets."""
    assert infer_meal_type(datetime(2026, 1, 1, 8, 0)) == MealType.BREAKFAST
    assert infer_meal_type(datetime(2026, 1, 1, 13, 0)) == MealType.LUNCH
    assert infer_meal_type(datetime(2026, 1, 1, 19, 0)) == MealType.DINNER
    assert infer_meal_type(datetime(2026, 1, 1, 23, 0)) == MealType.SNACK
