import pytest
from pydantic import ValidationError

from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService


def test_validates_food_recognition_json() -> None:
    """AI photo JSON should validate against the expected schema."""
    result = FoodRecognitionResult.model_validate_json(
        """
        {
          "items": [
            {
              "name": "рис",
              "portion_description": "примерно половина тарелки",
              "estimated_grams": 180,
              "calories": 230,
              "protein": 4,
              "fat": 1,
              "carbs": 50,
              "confidence": 0.82
            }
          ],
          "total_calories": 230,
          "overall_confidence": 0.82,
          "comment": "Это приблизительная оценка."
        }
        """
    )

    assert result.items[0].name == "рис"
    assert result.total_calories == 230


def test_rejects_invalid_confidence() -> None:
    """Confidence must be between 0 and 1."""
    with pytest.raises(ValidationError):
        FoodRecognitionResult.model_validate(
            {
                "items": [
                    {
                        "name": "рис",
                        "portion_description": "порция",
                        "estimated_grams": 100,
                        "calories": 130,
                        "protein": None,
                        "fat": None,
                        "carbs": None,
                        "confidence": 1.5,
                    }
                ],
                "total_calories": 130,
                "overall_confidence": 1.5,
                "comment": "Оценка.",
            }
        )


def test_calorie_service_updates_grams_and_recalculates_total() -> None:
    """Changing grams should proportionally update calories and total."""
    result = FoodRecognitionResult.model_validate(
        {
            "items": [
                {
                    "name": "рис",
                    "portion_description": "порция",
                    "estimated_grams": 200,
                    "calories": 260,
                    "protein": 5,
                    "fat": 1,
                    "carbs": 56,
                    "confidence": 0.8,
                }
            ],
            "total_calories": 260,
            "overall_confidence": 0.8,
            "comment": "Оценка.",
        }
    )

    updated = CalorieService().update_grams(result, index=1, grams=100)

    assert updated.items[0].calories == 130
    assert updated.total_calories == 130
