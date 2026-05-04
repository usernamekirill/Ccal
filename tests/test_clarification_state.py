"""FSM payload helpers for clarification."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.services.calorie_service import CalorieService
from calorie_bot.app.utils.clarification_state import fsm_data_blocking_text_clarification


def test_fsm_skips_text_draft_when_items_empty() -> None:
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[],
        total_calories=0,
        overall_confidence=0.5,
        comment="x",
    )
    r = svc.validate_food_result(r)
    data = fsm_data_blocking_text_clarification(svc, r, pending_text="яблоко", default_meal_type="lunch")
    assert data["clarification_mode"] is None
    assert data["pending_food_result_draft"] is None
    assert data["pending_text_food"] == "яблоко"


def test_fsm_uses_text_draft_when_items_present() -> None:
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="Яблоко",
                portion_description="100 г",
                estimated_grams=100.0,
                calories=50,
                calories_per_100g=50.0,
                protein=0.3,
                fat=0.2,
                carbs=12.0,
                food_confidence=0.9,
                portion_confidence=0.9,
                confidence=0.9,
            )
        ],
        total_calories=50,
        overall_confidence=0.7,
        comment="x",
        needs_clarification=True,
        clarification_question="Уточните сорт",
    )
    r = svc.validate_food_result(r)
    data = fsm_data_blocking_text_clarification(svc, r, pending_text="яблоко", default_meal_type="lunch")
    assert data["clarification_mode"] == "text_draft"
    assert data["pending_food_result_draft"] is not None
