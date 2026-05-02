from calorie_bot.app.ai.schemas import FoodRecognitionResult
from calorie_bot.app.services.correction_service import CorrectionService


def test_voice_correction_updates_grams_and_adds_item() -> None:
    """Voice correction should update current photo draft and keep it confirmable."""
    current = FoodRecognitionResult.model_validate(
        {
            "items": [
                {
                    "name": "рис",
                    "portion_description": "200 г",
                    "estimated_grams": 200,
                    "calories": 260,
                    "protein": 5,
                    "fat": 1,
                    "carbs": 56,
                    "confidence": 0.82,
                }
            ],
            "total_calories": 260,
            "overall_confidence": 0.82,
            "comment": "Это приблизительная оценка.",
        }
    )

    updated = CorrectionService().apply_food_result_correction(
        current,
        "риса было не 200 грамм, а 120, и добавь соус",
    )

    assert updated.items[0].estimated_grams == 120
    assert updated.items[0].calories == 156
    assert updated.items[1].name == "соус"
    assert updated.items[1].calories is None
    assert updated.items[1].needs_portion_clarification is True
    assert updated.total_calories == 156


def test_voice_correction_deletes_item_by_name() -> None:
    """Voice correction should delete an item by natural-language name."""
    current = FoodRecognitionResult.model_validate(
        {
            "items": [
                {
                    "name": "рис",
                    "portion_description": "200 г",
                    "estimated_grams": 200,
                    "calories": 260,
                    "protein": None,
                    "fat": None,
                    "carbs": None,
                    "confidence": 0.8,
                },
                {
                    "name": "соус",
                    "portion_description": "немного",
                    "estimated_grams": 30,
                    "calories": 70,
                    "protein": None,
                    "fat": None,
                    "carbs": None,
                    "confidence": 0.7,
                },
            ],
            "total_calories": 330,
            "overall_confidence": 0.7,
            "comment": "Это приблизительная оценка.",
        }
    )

    updated = CorrectionService().apply_food_result_correction(current, "убери соус")

    assert [item.name for item in updated.items] == ["рис"]
    assert updated.total_calories == 260


def test_voice_correction_deletes_second_item_by_ordinal() -> None:
    """Phrases like «убери второе» should drop the 2nd draft line without double-deleting by name."""
    current = FoodRecognitionResult.model_validate(
        {
            "items": [
                {
                    "name": "рис",
                    "portion_description": "200 г",
                    "estimated_grams": 200,
                    "calories": 260,
                    "protein": None,
                    "fat": None,
                    "carbs": None,
                    "confidence": 0.8,
                },
                {
                    "name": "соус",
                    "portion_description": "немного",
                    "estimated_grams": 30,
                    "calories": 70,
                    "protein": None,
                    "fat": None,
                    "carbs": None,
                    "confidence": 0.7,
                },
                {
                    "name": "салат",
                    "portion_description": "100 г",
                    "estimated_grams": 100,
                    "calories": 50,
                    "confidence": 0.7,
                },
            ],
            "total_calories": 380,
            "overall_confidence": 0.7,
            "comment": "",
        }
    )

    updated = CorrectionService().apply_food_result_correction(current, "убери второе")

    assert [item.name for item in updated.items] == ["рис", "салат"]
