"""Rule-based clarification guards."""

from calorie_bot.app.ai.schemas import FoodItemRecognition, FoodRecognitionResult
from calorie_bot.app.domain import GramsSource
from calorie_bot.app.services.calorie_service import CalorieService


def test_guard_triggers_on_ambiguous_cheese_with_default_portion() -> None:
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="Сыр",
                portion_description="40 г",
                estimated_grams=40.0,
                calories=150,
                calories_per_100g=375.0,
                protein=10.0,
                fat=12.0,
                carbs=2.0,
                food_confidence=0.85,
                portion_confidence=0.55,
                grams_source=GramsSource.DEFAULT_PORTION.value,
                confidence=0.85,
            )
        ],
        total_calories=150,
        overall_confidence=0.85,
        comment="t",
    )
    out = svc.validate_food_result(r)
    guarded = svc.apply_clarification_guards(out)
    assert guarded.needs_clarification is True
    assert guarded.clarification_question
    assert "Сыр" in guarded.clarification_question or "сыр" in guarded.clarification_question.lower()


def test_guard_skips_when_user_gave_grams() -> None:
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[
            FoodItemRecognition(
                name="сыр",
                portion_description="50 г",
                estimated_grams=50.0,
                calories=200,
                calories_per_100g=400.0,
                protein=12.0,
                fat=15.0,
                carbs=1.0,
                food_confidence=0.9,
                portion_confidence=0.9,
                grams_source=GramsSource.USER.value,
                confidence=0.9,
            )
        ],
        total_calories=200,
        overall_confidence=0.9,
        comment="t",
    )
    out = svc.validate_food_result(r)
    guarded = svc.apply_clarification_guards(out)
    assert guarded.needs_clarification is False
    assert not (guarded.clarification_question or "").strip()


def test_guard_empty_items_sets_blocking_question() -> None:
    """Empty parse must not fall through silent; user gets a clarification (spec: no silent miss)."""
    svc = CalorieService()
    r = FoodRecognitionResult(
        items=[],
        total_calories=0,
        overall_confidence=0.5,
        comment="t",
    )
    out = svc.validate_food_result(r)
    guarded = svc.apply_clarification_guards(out)
    assert guarded.needs_clarification is True
    assert guarded.clarification_question
    assert "грамм" in guarded.clarification_question.lower() or "калор" in guarded.clarification_question.lower()
